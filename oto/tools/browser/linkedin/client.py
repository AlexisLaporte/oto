"""LinkedIn Client — browser automation with rate limiting and multi-account support."""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Dict

from o_browser import BrowserClient
from oto.tools.common.rate_limiter import LinkedInRateLimiter
from oto.config import get_sessions_dir, get_secret
from .scrape import ProfileMixin, CompanyMixin, MessagesMixin
from .search import SearchMixin


def get_worker_cookie(
    api_url: str = None,
    api_key: str = None,
    action: str = "profile_visit",
) -> dict:
    """Fetch LinkedIn cookie from otomata-worker API.

    Returns:
        {"cookie": str, "user_agent": str|None, "identity_name": str, "account_type": str}

    Raises:
        RuntimeError: If worker is unreachable or no identity available
    """
    import urllib.request

    url = api_url or get_secret("OTOMATA_API_URL")
    key = api_key or get_secret("OTOMATA_API_KEY")

    if not url:
        raise RuntimeError(
            "OTOMATA_API_URL not set. Configure it in env or ~/.otomata/secrets.env"
        )

    endpoint = f"{url.rstrip('/')}/identities/available?platform=linkedin&action={action}"
    headers = {"Accept": "application/json"}
    if key:
        headers["X-API-Key"] = key

    req = urllib.request.Request(endpoint, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("No available LinkedIn identity on worker") from e
        raise RuntimeError(f"Worker API error: {e.code}") from e
    except Exception as e:
        raise RuntimeError(f"Cannot reach worker at {url}: {e}") from e


MAX_SESSIONS_PER_IDENTITY = 3
SEMAPHORE_DIR = Path("/tmp/linkedin_sessions")


class LinkedInClient(ProfileMixin, CompanyMixin, MessagesMixin, SearchMixin, BrowserClient):
    """
    LinkedIn automation client with:
    - Cookie-based authentication
    - Rate limiting (10/h, 80/day profile visits for free accounts)
    - Identity management for multi-account support
    - Company and profile scraping
    """

    def __init__(
        self,
        cookie: str = None,
        identity: str = "default",
        profile: str = None,
        headless: bool = True,
        channel: str = None,
        rate_limit: bool = True,
        account_type: str = "free",
        user_agent: str = None,
        cdp_url: str = None,
    ):
        self.identity = identity
        self.rate_limit_enabled = rate_limit
        self.account_type = account_type
        self._use_profile = profile is not None or cdp_url is not None

        # Get cookie from arg or secrets (not needed with profile/cdp)
        self._li_at_cookie = cookie or get_secret("LINKEDIN_COOKIE")
        resolved_user_agent = user_agent or get_secret("LINKEDIN_USER_AGENT")

        # Allow disabling rate limit via env var (for automated agent jobs)
        if os.environ.get("LINKEDIN_NO_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
            self.rate_limit_enabled = False

        if not self._li_at_cookie and not profile and not cdp_url:
            session_file = get_sessions_dir() / "linkedin.json"
            if session_file.exists():
                data = json.loads(session_file.read_text())
                self._li_at_cookie = data.get("cookie") or data.get("li_at")
                resolved_user_agent = resolved_user_agent or data.get("user_agent")

        if not self._li_at_cookie and not profile and not cdp_url:
            raise ValueError(
                "LinkedIn cookie required. Provide via:\n"
                "  - cookie parameter\n"
                "  - LINKEDIN_COOKIE env var\n"
                "  - --profile <path> (Chrome profile with LinkedIn session)\n"
                "  - --cdp-url <url> (connect to existing Chrome)\n"
                "  - ~/.config/otomata/sessions/linkedin.json"
            )

        super().__init__(
            profile_path=profile,
            headless=headless,
            channel=channel,
            viewport=(1920, 1080),
            user_agent=resolved_user_agent,
            cdp_url=cdp_url,
        )

        self._rate_limiters: Dict[str, LinkedInRateLimiter] = {}
        self._slot_file = None

    # --- Session slot management (limit concurrent sessions per identity) ---

    def _acquire_slot(self):
        SEMAPHORE_DIR.mkdir(exist_ok=True)

        for slot_file in SEMAPHORE_DIR.glob("slot_*"):
            try:
                if time.time() - slot_file.stat().st_mtime > 600:
                    slot_file.unlink()
            except Exception:
                pass

        for i in range(MAX_SESSIONS_PER_IDENTITY):
            slot_path = SEMAPHORE_DIR / f"slot_{self.identity}_{i}"
            try:
                fd = os.open(slot_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self._slot_file = slot_path
                return
            except FileExistsError:
                continue

        raise RuntimeError(
            f"Identity '{self.identity}' already has {MAX_SESSIONS_PER_IDENTITY} active session(s). "
            f"Wait or use a different identity."
        )

    def _release_slot(self):
        if self._slot_file and self._slot_file.exists():
            try:
                self._slot_file.unlink()
            except Exception:
                pass
        self._slot_file = None

    # --- Lifecycle ---

    async def __aenter__(self):
        self._acquire_slot()
        await super().start()

        if not self._use_profile and self._li_at_cookie:
            await self.add_cookies([{
                "name": "li_at",
                "value": self._li_at_cookie,
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            }])

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await super().close()
        finally:
            self._release_slot()

    # --- Rate limiting ---

    def _get_rate_limiter(self, action_type: str) -> LinkedInRateLimiter:
        if action_type not in self._rate_limiters:
            self._rate_limiters[action_type] = LinkedInRateLimiter(
                identity=self.identity,
                action_type=action_type,
                account_type=self.account_type,
            )
        return self._rate_limiters[action_type]

    async def check_rate_limit(self, action_type: str = "profile_visit"):
        if not self.rate_limit_enabled:
            return

        limiter = self._get_rate_limiter(action_type)
        can_proceed, wait_time, reason = limiter.can_make_request()

        if not can_proceed:
            if reason == "outside_active_hours":
                raise RuntimeError(
                    f"Outside active hours for {action_type}. "
                    f"Resume at {limiter.next_active_time()}"
                )

            if reason == "random_skip":
                jitter = random.randint(30, 90)
                print(f"Random skip ({action_type}): waiting {jitter}s")
                await asyncio.sleep(jitter)
                return

            if wait_time < 300:
                print(f"Rate limit ({action_type}/{reason}): waiting {wait_time}s")
                await asyncio.sleep(wait_time)
            else:
                raise RuntimeError(
                    f"Rate limit exceeded for {action_type}. Wait {wait_time}s "
                    f"(until {limiter.can_make_request_at()})"
                )

        limiter.record_request()
