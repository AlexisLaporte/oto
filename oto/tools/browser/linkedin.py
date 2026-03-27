"""
LinkedIn Client - Browser automation for LinkedIn with rate limiting.

Inherits from BrowserClient for browser management.
"""

import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

from o_browser import BrowserClient
from ..common.rate_limiter import LinkedInRateLimiter
from ...config import get_sessions_dir, get_secret


def get_worker_cookie(
    api_url: str = None,
    api_key: str = None,
    action: str = "profile_visit",
) -> dict:
    """Fetch LinkedIn cookie from otomata-worker API.

    Args:
        api_url: Worker API URL (default: OTOMATA_API_URL secret)
        api_key: API key (default: OTOMATA_API_KEY secret)
        action: Action type for rate limit check

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


# Semaphore: max concurrent sessions PER IDENTITY
MAX_SESSIONS_PER_IDENTITY = 3
SEMAPHORE_DIR = Path("/tmp/linkedin_sessions")


class LinkedInClient(BrowserClient):
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
        """
        Initialize LinkedIn client.

        Args:
            cookie: li_at cookie value (or set LINKEDIN_COOKIE env var).
                    Not needed if using a profile or cdp_url.
            identity: Identity name for rate limiting separation
            profile: Path to Chrome profile directory (persistent session).
                     If set, cookies from the profile are used directly.
            headless: Run browser in headless mode
            channel: Chrome channel (chrome, chrome-beta, chromium)
            rate_limit: Enforce rate limiting
            account_type: Account type for rate limits (free, premium, sales_navigator)
            user_agent: Custom user agent
            cdp_url: Connect to an existing Chrome via CDP (e.g. "http://127.0.0.1:9222").
                     Uses the browser's existing session — no cookie needed.
        """
        self.identity = identity
        self.rate_limit_enabled = rate_limit
        self.account_type = account_type
        self._use_profile = profile is not None or cdp_url is not None

        # Get cookie from arg or env or session file (not needed with profile/cdp)
        self._li_at_cookie = cookie or os.environ.get("LINKEDIN_COOKIE")
        resolved_user_agent = user_agent or os.environ.get("LINKEDIN_USER_AGENT")

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

        # Initialize base BrowserClient
        super().__init__(
            profile_path=profile,
            headless=headless,
            channel=channel,
            viewport=(1920, 1080),
            user_agent=resolved_user_agent,
            cdp_url=cdp_url,
        )

        self._rate_limiters = {}
        self._slot_file = None

    def _get_rate_limiter(self, action_type: str) -> LinkedInRateLimiter:
        """Get or create a rate limiter for the given action type."""
        if action_type not in self._rate_limiters:
            self._rate_limiters[action_type] = LinkedInRateLimiter(
                identity=self.identity,
                action_type=action_type,
                account_type=self.account_type,
            )
        return self._rate_limiters[action_type]

    def _acquire_slot(self):
        """Acquire a session slot for this identity (limit concurrent sessions)."""
        SEMAPHORE_DIR.mkdir(exist_ok=True)

        # Clean stale slots (older than 10 minutes)
        for slot_file in SEMAPHORE_DIR.glob("slot_*"):
            try:
                if time.time() - slot_file.stat().st_mtime > 600:
                    slot_file.unlink()
            except Exception:
                pass

        # Try to acquire a slot for this identity
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
        """Release the session slot."""
        if self._slot_file and self._slot_file.exists():
            try:
                self._slot_file.unlink()
            except Exception:
                pass
        self._slot_file = None

    async def __aenter__(self):
        """Start browser, acquire slot, and inject LinkedIn cookie."""
        self._acquire_slot()

        # Start browser via parent
        await super().start()

        # Inject LinkedIn cookie (skip when using a Chrome profile that already has cookies)
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
        """Close browser and release slot."""
        try:
            await super().close()
        finally:
            self._release_slot()

    async def check_rate_limit(self, action_type: str = "profile_visit"):
        """Check and enforce rate limiting."""
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

    async def scrape_company(self, url: str) -> dict:
        """
        Scrape LinkedIn company page.

        Returns:
            {url, name, tagline, about, website, phone, industry, size, founded, headquarters, company_id}
        """
        await self.check_rate_limit("company_scrape")

        about_url = url.rstrip("/") + "/about/"
        await self.goto(about_url)
        await self.wait(2)

        data = {"url": url}

        # Extract company ID
        html = await self.get_html()
        match = re.search(r"urn:li:fs_normalized_company:(\d+)", html)
        if match:
            data["company_id"] = match.group(1)

        # Company name
        h1 = await self.query_selector("h1")
        if h1:
            data["name"] = (await h1.inner_text()).strip()

        # Tagline
        tagline = await self.query_selector(".org-top-card-summary__tagline")
        if tagline:
            data["tagline"] = (await tagline.inner_text()).strip()

        # About text
        for selector in ["p.break-words", '[data-test-id="about-us__description"]']:
            el = await self.query_selector(selector)
            if el:
                text = (await el.inner_text()).strip()
                if len(text) > 50:
                    data["about"] = text
                    break

        # Extract dt/dd pairs
        dt_elements = await self.query_selector_all("dt")
        for dt in dt_elements:
            label = (await dt.inner_text()).strip().lower()
            dd = await dt.evaluate_handle("el => el.nextElementSibling")
            if dd:
                value = (await dd.inner_text()).strip()

                if "site web" in label or "website" in label:
                    data["website"] = value
                elif "téléphone" in label or "phone" in label:
                    data["phone"] = value.split("\n")[0]
                elif "secteur" in label or "industry" in label:
                    data["industry"] = value
                elif "taille" in label or "company size" in label:
                    data["size"] = value.split("\n")[0]
                elif "fondée" in label or "founded" in label:
                    data["founded"] = value
                elif "siège" in label or "headquarters" in label:
                    data["headquarters"] = value

        return data

    async def scrape_profile(self, url: str) -> dict:
        """
        Scrape LinkedIn profile page.

        Returns:
            {url, name, headline, location, about}
        """
        await self.check_rate_limit("profile_visit")

        await self.goto(url)
        await self.wait(2)

        data = {"url": url}

        # Name
        name_selectors = [
            "h1.text-heading-xlarge",
            "h1.inline.t-24",
            ".pv-text-details__left-panel h1",
            "h1",
        ]
        for selector in name_selectors:
            name_el = await self.query_selector(selector)
            if name_el:
                name = (await name_el.inner_text()).strip()
                if name and len(name) > 1:
                    data["name"] = name
                    break

        # Headline
        headline_selectors = [
            ".text-body-medium.break-words",
            ".pv-text-details__left-panel .text-body-medium",
        ]
        for selector in headline_selectors:
            headline = await self.query_selector(selector)
            if headline:
                text = (await headline.inner_text()).strip()
                if text and len(text) > 3:
                    data["headline"] = text
                    break

        # Location
        location_selectors = [
            ".text-body-small.inline.t-black--light.break-words",
            ".pv-text-details__left-panel .text-body-small",
        ]
        for selector in location_selectors:
            location = await self.query_selector(selector)
            if location:
                text = (await location.inner_text()).strip()
                if text:
                    data["location"] = text
                    break

        # About section
        about = await self.query_selector("#about ~ div .inline-show-more-text")
        if about:
            data["about"] = (await about.inner_text()).strip()

        return data

    async def get_company_id(self, company_slug: str) -> Optional[str]:
        """Get numeric company ID from slug."""
        await self.check_rate_limit("company_scrape")

        url = f"https://www.linkedin.com/company/{company_slug}/"
        await self.goto(url)
        await self.wait(2)

        html = await self.get_html()
        match = re.search(r"urn:li:fs_normalized_company:(\d+)", html)
        return match.group(1) if match else None

    async def search_employees(
        self, company_slug: str, keywords: List[str] = None, limit: int = 10
    ) -> List[dict]:
        """
        Search employees via LinkedIn search with company filter.

        Args:
            company_slug: LinkedIn company slug
            keywords: Title keywords to search
            limit: Max employees to return

        Returns:
            List of {name, headline, linkedin}
        """
        company_id = await self.get_company_id(company_slug)
        if not company_id:
            return []

        await self.check_rate_limit("search_export")

        kw_str = " OR ".join(keywords) if keywords else ""
        search_url = f'https://www.linkedin.com/search/results/people/?currentCompany=%5B%22{company_id}%22%5D&keywords={quote(kw_str)}&origin=FACETED_SEARCH'

        await self.goto(search_url)
        await self.wait(4)

        # Scroll to load results
        for i in range(8):
            await self.scroll_by((i + 1) * 400)
            await self.wait(1.5)

        employees = []
        seen_urls = set()
        seen_names = set()

        links = await self.query_selector_all('a[href*="/in/"]')

        for link in links:
            if len(employees) >= limit:
                break

            href = await link.get_attribute("href")
            if not href:
                continue

            url = href.split("?")[0]
            if url in seen_urls or "/in/" not in url:
                continue

            text = await link.inner_text()
            if not text or len(text.strip()) < 3:
                continue

            lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
            if len(lines) < 3:
                continue

            name = re.sub(r"\s*•.*$", "", lines[0]).strip()
            if len(name) < 3 or name.lower() in ["voir", "view", "message", "suivre", "follow"]:
                continue

            seen_urls.add(url)

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Find headline
            headline = ""
            for line in lines[1:]:
                line_stripped = line.strip()
                if re.match(r"^•\s*\d*(st|nd|rd|th|er?|e)?\+?", line_stripped, re.IGNORECASE):
                    continue
                if line_stripped.lower() in ["message", "suivre", "follow", "se connecter", "connect"]:
                    continue
                headline = line_stripped
                break

            employees.append({
                "name": name,
                "headline": headline,
                "linkedin": url
            })

        return employees

    async def get_company_people(self, company_slug: str, limit: int = 20) -> List[dict]:
        """
        Get employees from company's People page (sorted by relevance).

        Args:
            company_slug: LinkedIn company slug
            limit: Max employees to return

        Returns:
            List of {name, headline, linkedin}
        """
        await self.check_rate_limit("search_export")

        people_url = f"https://www.linkedin.com/company/{company_slug}/people/"
        await self.goto(people_url)
        await self.wait(3)

        # Load more results
        for _ in range(limit // 12 + 1):
            await self.scroll_to_bottom(times=1, delay=1)

            show_more = await self.query_selector("button.scaffold-finite-scroll__load-button")
            if show_more:
                try:
                    await show_more.click()
                    await self.wait(2)
                except:
                    break
            else:
                break

        employees = []
        seen_urls = set()

        cards = await self.query_selector_all("li.org-people-profile-card__profile-card-spacing")

        for card in cards:
            if len(employees) >= limit:
                break

            link = await card.query_selector('a[href*="/in/"]')
            if not link:
                continue

            href = await link.get_attribute("href")
            if not href:
                continue

            url = href.split("?")[0]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            name = ""
            name_el = await card.query_selector(".artdeco-entity-lockup__title")
            if name_el:
                name = (await name_el.inner_text()).strip()
                name = re.sub(r"\s*·\s*\d*(er?|e|st|nd|rd|th)?\+?$", "", name).strip()

            if not name or len(name) < 2:
                continue

            headline = ""
            headline_el = await card.query_selector(".artdeco-entity-lockup__subtitle")
            if headline_el:
                headline = (await headline_el.inner_text()).strip()

            employees.append({
                "name": name,
                "headline": headline,
                "linkedin": url
            })

        return employees

    async def scrape_profile_posts(self, url: str, max_posts: int = 10) -> List[dict]:
        """
        Scrape posts from a LinkedIn profile's activity feed.

        Args:
            url: Profile URL (e.g. https://www.linkedin.com/in/alexislaporte/)
            max_posts: Maximum number of posts to retrieve

        Returns:
            List of {content, date, url, is_repost, engagement: {reactions, comments}}
        """
        await self.check_rate_limit("profile_visit")

        activity_url = url.rstrip("/") + "/recent-activity/all/"
        await self.goto(activity_url)
        await self.wait(3)

        posts = []
        last_count = 0
        stale_rounds = 0

        # Scroll to load posts
        for i in range(max_posts // 2 + 3):
            await self.scroll_by(random.randint(400, 700))
            await self.wait(random.uniform(1.5, 2.5))

            items = await self.query_selector_all(".feed-shared-update-v2")
            if len(items) >= max_posts:
                break
            if len(items) == last_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
                last_count = len(items)

        items = await self.query_selector_all(".feed-shared-update-v2")

        for item in items:
            if len(posts) >= max_posts:
                break

            # Post content
            content_el = await item.query_selector(".break-words")
            if not content_el:
                content_el = await item.query_selector(".update-components-text")
            content = (await content_el.inner_text()).strip() if content_el else ""

            if not content:
                continue

            # Date
            date = ""
            time_el = await item.query_selector("time")
            if time_el:
                date = await time_el.get_attribute("datetime") or ""

            # Post URL
            post_url = ""
            urn = await item.get_attribute("data-urn")
            if urn:
                activity_id = urn.split(":")[-1]
                post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"

            # Is repost
            is_repost = False
            header = await item.query_selector(".update-components-header__text-view")
            if header:
                header_text = (await header.inner_text()).lower()
                is_repost = "repost" in header_text or "a republié" in header_text

            # Engagement
            reactions = 0
            comments = 0
            social_counts = await item.query_selector(".social-details-social-counts")
            if social_counts:
                text = (await social_counts.inner_text()).strip()
                r_match = re.search(r"(\d[\d\s,.]*)\s*(reaction|j'aime|like)", text, re.IGNORECASE)
                if r_match:
                    reactions = int(re.sub(r"[\s,.]", "", r_match.group(1)))
                c_match = re.search(r"(\d[\d\s,.]*)\s*comment", text, re.IGNORECASE)
                if c_match:
                    comments = int(re.sub(r"[\s,.]", "", c_match.group(1)))

            posts.append({
                "content": content,
                "date": date,
                "url": post_url,
                "is_repost": is_repost,
                "engagement": {"reactions": reactions, "comments": comments},
            })

        return posts

    async def search_companies(self, query: str, limit: int = 5) -> List[dict]:
        """
        Search companies on LinkedIn.

        Returns:
            List of {name, slug, url, headline}
        """
        await self.check_rate_limit("search_export")

        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={quote(query)}&origin=SWITCH_SEARCH_VERTICAL"
        await self.goto(search_url)
        await self.wait(3)

        for i in range(3):
            await self.scroll_by((i + 1) * 400)
            await self.wait(1)

        companies = []
        seen_slugs = set()

        # Find all company links and extract info from their parent containers
        links = await self.query_selector_all('a[href*="/company/"]')

        for link in links:
            if len(companies) >= limit:
                break

            href = await link.get_attribute("href")
            if not href or "/company/" not in href:
                continue

            match = re.search(r"/company/([^/?]+)", href)
            if not match:
                continue

            slug = match.group(1)
            if slug in seen_slugs or slug in ("login", "signup"):
                continue
            seen_slugs.add(slug)

            # Get text from the link or its parent
            text = (await link.inner_text()).strip()
            if not text or len(text) < 2:
                continue

            # First non-empty line is usually the name
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            name = lines[0]
            # Skip nav/button text
            if name.lower() in ["follow", "suivre", "message", "view", "voir"]:
                continue

            headline = lines[1] if len(lines) > 1 else ""

            url = f"https://www.linkedin.com/company/{slug}/"

            companies.append({
                "name": name,
                "slug": slug,
                "url": url,
                "headline": headline
            })

        return companies

    async def search_people(
        self, keywords: str, geo: str = None, network: str = None,
        limit: int = 50, pages: int = 5,
    ) -> List[dict]:
        """
        Search people on LinkedIn by keywords (title, skills, etc.) with optional geo/network filter.

        Args:
            keywords: Search keywords (e.g., "credit manager")
            geo: Geo URN ID for location filter (e.g., "105015875" for France)
            network: Connection degree filter — "F" (1st), "S" (2nd), "O" (3rd+)
            limit: Max results to return
            pages: Max pages to scrape (10 results per page)

        Returns:
            List of {name, headline, linkedin, location}
        """
        results = []
        seen_urls = set()

        for page in range(1, pages + 1):
            if len(results) >= limit:
                break

            await self.check_rate_limit("search_export")

            params = f"keywords={quote(keywords)}&origin=FACETED_SEARCH"
            if geo:
                params += f"&geoUrn=%5B%22{geo}%22%5D"
            if network:
                params += f"&network=%5B%22{network}%22%5D"
            if page > 1:
                params += f"&page={page}"

            search_url = f"https://www.linkedin.com/search/results/people/?{params}"
            await self.goto(search_url)
            await self.wait(4)

            # Scroll to load all results on page
            for i in range(8):
                await self.scroll_by((i + 1) * 400)
                await self.wait(1)

            # Parse result cards
            links = await self.query_selector_all('a[href*="/in/"]')
            page_count = 0

            for link in links:
                if len(results) >= limit:
                    break

                href = await link.get_attribute("href")
                if not href:
                    continue

                url = href.split("?")[0]
                if url in seen_urls or "/in/" not in url:
                    continue

                text = await link.inner_text()
                if not text or len(text.strip()) < 3:
                    continue

                lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
                if len(lines) < 2:
                    continue

                name = re.sub(r"\s*•.*$", "", lines[0]).strip()
                if len(name) < 3 or name.lower() in ["voir", "view", "message", "suivre", "follow", "se connecter", "connect"]:
                    continue

                seen_urls.add(url)

                # Extract headline (skip connection degree indicators)
                headline = ""
                location = ""
                for line in lines[1:]:
                    stripped = line.strip()
                    if re.match(r"^•?\s*\d*(st|nd|rd|th|er?|e)?\+?$", stripped, re.IGNORECASE):
                        continue
                    if stripped.lower() in ["message", "suivre", "follow", "se connecter", "connect"]:
                        continue
                    if not headline:
                        headline = stripped
                    elif not location:
                        location = stripped
                        break

                results.append({
                    "name": name,
                    "headline": headline,
                    "linkedin": url,
                    "location": location,
                })
                page_count += 1

            print(f"  Page {page}: {page_count} results (total: {len(results)})")

            # No results on this page = no more pages
            if page_count == 0:
                break

        return results
