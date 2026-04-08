"""Google Search via browser automation."""

from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

from o_browser import BrowserClient


class GoogleSearchClient(BrowserClient):
    """Google search via browser — uses Chrome profile to avoid bot detection."""

    def __init__(
        self,
        headless: bool = False,
        profile_path: Optional[str] = None,
        channel: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            headless=headless,
            profile_path=profile_path,
            channel=channel,
            **kwargs,
        )

    async def search(self, query: str, num: int = 10) -> Dict[str, Any]:
        """
        Search Google and extract organic results.

        Returns dict with 'organic' array matching Serper output format.
        """
        url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=fr"
        await self.goto(url)
        await self.wait(3)

        # Handle cookie consent if present
        consent_btn = await self.query_selector(
            'button#L2AGLb, form[action*="consent"] button'
        )
        if consent_btn:
            await consent_btn.click()
            await self.wait(1)

        # Check for bot detection
        text = await self.get_text()
        if "trafic exceptionnel" in text or "unusual traffic" in text:
            raise RuntimeError(
                "Google bot detection triggered. Use a Chrome profile: "
                "oto browser google -q 'query' --profile ~/.config/google-chrome/Default"
            )

        results = await self._extract_results(num)
        return {
            "searchParameters": {"q": query, "num": num, "engine": "google-browser"},
            "organic": results,
        }

    async def _extract_results(self, num: int) -> List[Dict[str, Any]]:
        """Extract organic results by finding h3 elements in search results."""
        results = []

        h3s = await self.query_selector_all("#rso h3, #search h3")
        if not h3s:
            h3s = await self.query_selector_all("h3")

        for h3 in h3s[:num]:
            try:
                data = await h3.evaluate("""el => {
                    const a = el.closest('a');
                    if (!a || !a.href || !a.href.startsWith('http')) return null;

                    // Walk up to find the result container
                    let container = el.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!container || !container.parentElement) break;
                        container = container.parentElement;
                        // Stop at a reasonable container size
                        if (container.offsetHeight > 120) break;
                    }

                    let snippet = null;
                    if (container) {
                        const title = el.innerText;
                        const full = container.innerText;
                        const rest = full.replace(title, '').trim();
                        const lines = rest.split('\\n').filter(l => l.trim().length > 30);
                        snippet = lines.slice(0, 2).join(' ') || null;
                    }

                    return {
                        title: el.innerText.trim(),
                        link: a.href,
                        snippet: snippet,
                    };
                }""")

                if data and data.get("title") and data.get("link"):
                    data["position"] = len(results) + 1
                    results.append(data)

            except Exception:
                continue

        return results
