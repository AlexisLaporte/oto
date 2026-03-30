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
        await self.wait(4)

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

        # About text: find the "Overview"/"Vue d'ensemble" section
        about_data = await self.page.evaluate("""() => {
            const r = {};
            // Find the section that contains Overview/Vue d'ensemble
            const sections = document.querySelectorAll('section');
            for (const s of sections) {
                const h2 = s.querySelector('h2');
                if (!h2) continue;
                const title = h2.textContent.trim().toLowerCase();
                const t = title.replace(/[\u2018\u2019\u0060]/g, "'");
                if (t.includes('overview') || t.includes("vue d'ensemble")) {
                    // Get the longest paragraph in this section
                    const ps = [...s.querySelectorAll('p')];
                    let best = '';
                    for (const p of ps) {
                        const t = p.textContent.trim();
                        if (t.length > best.length) best = t;
                    }
                    if (best.length > 30) r.about = best;
                    break;
                }
            }
            // Tagline: first p directly after h1 with short text
            const h1 = document.querySelector('h1');
            if (h1) {
                const section = h1.closest('section') || h1.parentElement;
                if (section) {
                    const ps = [...section.querySelectorAll('p')];
                    for (const p of ps) {
                        const t = p.textContent.trim();
                        if (t.length > 5 && t.length < 200) {
                            r.tagline = t;
                            break;
                        }
                    }
                }
            }
            return r;
        }""")
        if about_data.get("about"):
            data["about"] = about_data["about"]
        if about_data.get("tagline"):
            data["tagline"] = about_data["tagline"]

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
        await self.wait(3)

        data = {"url": url}

        # LinkedIn uses SDUI with hashed CSS classes — extract via JS + componentkey
        extracted = await self.page.evaluate("""() => {
            const r = {};
            // Topcard: name, headline, location
            const topcard = document.querySelector('section[componentkey*="Topcard"]');
            if (topcard) {
                const h2 = topcard.querySelector('h2');
                if (h2) r.name = h2.textContent.trim();
                // Collect all <p> texts in topcard
                const ps = [...topcard.querySelectorAll('p')].map(p => p.textContent.trim()).filter(t => t.length > 1);
                r._topcard_texts = ps;
            }
            // About section
            const about = document.querySelector('section[componentkey*="About"]');
            if (about) {
                const box = about.querySelector('[data-testid="expandable-text-box"]');
                if (box) {
                    r.about = box.textContent.trim();
                } else {
                    // Fallback: longest <p> in the about section
                    const ps = [...about.querySelectorAll('p')];
                    let best = '';
                    for (const p of ps) {
                        const t = p.textContent.trim();
                        if (t.length > best.length) best = t;
                    }
                    if (best.length > 20) r.about = best;
                }
            }
            return r;
        }""")

        if extracted.get("name"):
            data["name"] = extracted["name"]
        if extracted.get("about"):
            data["about"] = extracted["about"]

        # Parse topcard texts: filter out pronouns, connection degree, buttons
        skip_patterns = re.compile(
            r"^(·\s*\d|she/|he/|they/|coordonn|contact|message$|suivre$|follow$|"
            r"se connecter$|connect$|\d+\s*(relations?|connections?|abonnés|followers))",
            re.IGNORECASE,
        )
        topcard_texts = [
            t for t in extracted.get("_topcard_texts", [])
            if not skip_patterns.search(t) and t != data.get("name")
        ]
        # First remaining text = headline, then look for location pattern
        if topcard_texts:
            data["headline"] = topcard_texts[0]
        for t in topcard_texts[1:]:
            # Location typically contains a comma or country/region keywords
            if "," in t or any(kw in t.lower() for kw in [
                "france", "états-unis", "united", "paris", "london", "berlin",
                "région", "area", "metro", "périphérie",
            ]):
                data["location"] = t
                break

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

    # JS snippet: extract people search results from current page.
    # Uses computed font-size/weight to distinguish result names (16px/600)
    # from mutual connection links (12px/400), since CSS classes are hashed.
    _JS_EXTRACT_PEOPLE_RESULTS = r"""() => {
        const results = [];
        const seen = new Set();
        const links = document.querySelectorAll('a[href*="/in/"]');

        for (const link of links) {
            const text = link.textContent.trim();
            if (text.length < 2 || text.length > 80) continue;
            if (link.parentElement?.tagName !== 'P') continue;

            const style = window.getComputedStyle(link.parentElement);
            if (parseFloat(style.fontSize) < 14 || parseInt(style.fontWeight) < 600) continue;

            const href = link.href?.split('?')[0];
            if (!href || !href.includes('/in/') || seen.has(href)) continue;
            seen.add(href);

            const name = text.replace(/\s+/g, ' ').trim();

            // Walk up to find the card-level <a> wrapping this result
            let cardLink = null;
            let el = link.parentElement;
            for (let i = 0; i < 10; i++) {
                if (!el) break;
                if (el.tagName === 'A' && el.href?.includes('/in/')) { cardLink = el; break; }
                el = el.parentElement;
            }

            let headline = '', location = '';
            if (cardLink) {
                const ps = [...cardLink.querySelectorAll('p')]
                    .map(p => p.textContent.trim()).filter(t => t.length > 1);
                let passedName = false;
                for (const p of ps) {
                    if (p.includes(name.substring(0, Math.min(name.length, 6)))) {
                        passedName = true; continue;
                    }
                    if (!passedName) continue;
                    if (/^[•·]?\s*\d*(st|nd|rd|th|er?|e)?\+?$/i.test(p)) continue;
                    if (/^(message|suivre|follow|se connecter|connect)$/i.test(p)) continue;
                    if (!headline) headline = p;
                    else if (!location) { location = p; break; }
                }
            }

            results.push({name, headline, location, linkedin: href});
        }
        return results;
    }"""

    async def _extract_people_results(self) -> List[dict]:
        """Extract people search results from the current page via JS."""
        return await self.page.evaluate(self._JS_EXTRACT_PEOPLE_RESULTS)

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

        for i in range(8):
            await self.scroll_by((i + 1) * 400)
            await self.wait(1.5)

        results = await self._extract_people_results()
        return results[:limit]

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
        await self.wait(4)

        # Scroll to load posts (activity items use data-urn with activity URNs)
        last_count = 0
        stale_rounds = 0
        for i in range(max_posts // 2 + 3):
            await self.scroll_by(random.randint(400, 700))
            await self.wait(random.uniform(1.5, 2.5))

            count = await self.page.evaluate(
                'document.querySelectorAll("[data-urn*=\\"urn:li:activity\\"]").length'
            )
            if count >= max_posts:
                break
            if count == last_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
                last_count = count

        # Extract posts via JS (activity page uses Ember with data-urn attributes)
        posts = await self.page.evaluate(r"""(maxPosts) => {
            const items = document.querySelectorAll('[data-urn*="urn:li:activity"]');
            const posts = [];
            const seen = new Set();

            for (const item of items) {
                if (posts.length >= maxPosts) break;

                const urn = item.getAttribute('data-urn');
                if (!urn || seen.has(urn)) continue;
                // Skip comment URNs
                if (urn.includes('comment')) continue;
                seen.add(urn);

                // Post content: find the text div (skip social/actor/image sections)
                let content = '';
                const divs = item.querySelectorAll('div');
                const skipPattern = /social|actor|action-bar|image|video|comments?-list/i;
                for (const d of divs) {
                    const cls = d.className || '';
                    if (skipPattern.test(cls)) continue;
                    if (d.querySelectorAll('div').length > 3) continue;
                    const t = d.textContent.trim();
                    if (t.length > content.length && t.length > 30 && t.length < 10000) {
                        // Skip engagement-like content (starts with just a number)
                        if (/^\d+\s*$/.test(t.split('\n')[0].trim())) continue;
                        content = t;
                    }
                }
                if (!content || content.length < 20) continue;

                // Activity ID → URL
                const activityId = urn.match(/activity:(\d+)/)?.[1];
                const postUrl = activityId ?
                    'https://www.linkedin.com/feed/update/urn:li:activity:' + activityId + '/' : '';

                // Date: from sub-description or time element
                let date = '';
                const subDesc = item.querySelector('[class*="sub-description"]');
                if (subDesc) date = subDesc.textContent.trim().split('•')[0].trim();

                // Is repost
                let isRepost = false;
                const header = item.querySelector('[class*="header__text"]');
                if (header) {
                    const ht = header.textContent.toLowerCase();
                    isRepost = ht.includes('repost') || ht.includes('republié');
                }

                // Engagement
                let reactions = 0, comments = 0;
                const socialArea = item.querySelector('[class*="social-activity"], [class*="social-counts"]');
                if (socialArea) {
                    const text = socialArea.textContent;
                    const rMatch = text.match(/(\d[\d\s,.]*)\s*$/m);
                    // Count reactions from the first number-like pattern
                    const spans = socialArea.querySelectorAll('span');
                    for (const s of spans) {
                        const st = s.textContent.trim();
                        if (/personne|reaction|like|j'aime/i.test(st)) {
                            const m = st.match(/(\d[\d\s,.]*)/);
                            if (m) reactions = parseInt(m[1].replace(/[\s,.]/g, ''));
                        }
                        if (/comment/i.test(st)) {
                            const m = st.match(/(\d[\d\s,.]*)/);
                            if (m) comments = parseInt(m[1].replace(/[\s,.]/g, ''));
                        }
                    }
                }

                posts.push({
                    content, date, url: postUrl, is_repost: isRepost,
                    engagement: {reactions, comments}
                });
            }
            return posts;
        }""", max_posts)

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

            for i in range(8):
                await self.scroll_by((i + 1) * 400)
                await self.wait(1)

            page_results = await self._extract_people_results()
            page_count = 0
            for r in page_results:
                if len(results) >= limit:
                    break
                if r["linkedin"] in seen_urls:
                    continue
                seen_urls.add(r["linkedin"])
                results.append(r)
                page_count += 1

            print(f"  Page {page}: {page_count} results (total: {len(results)})")

            if page_count == 0:
                break

        return results
