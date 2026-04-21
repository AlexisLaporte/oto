"""SNCF Connect — trip listing and invoice/justificatif download."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from o_browser import BrowserClient

DEFAULT_PROFILE = str(Path.home() / ".config/browser/google")


class SNCFClient(BrowserClient):
    """SNCF Connect browser client — requires a logged-in Chrome profile."""

    def __init__(
        self,
        profile_path: Optional[str] = None,
        headless: bool = True,
        **kwargs,
    ):
        super().__init__(
            profile_path=profile_path or DEFAULT_PROFILE,
            headless=headless,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            **kwargs,
        )

    async def _dismiss_cookies(self):
        try:
            await self.click("button:has-text('Continuer sans accepter')")
            await self.wait(1)
        except Exception:
            pass

    async def _goto_trips(self, tab: str = "PASSED"):
        await self.goto("https://www.sncf-connect.com/trips")
        await self.wait(4)
        await self._dismiss_cookies()
        if tab:
            await self.evaluate(
                f"document.getElementById('nav-tab-{tab}')?.click()"
            )
            await self.wait(3)

    async def list_trips(self, past: bool = True) -> List[Dict[str, Any]]:
        """List trips (past or upcoming). Returns raw text blocks."""
        tab = "PASSED" if past else "UPCOMING"
        await self._goto_trips(tab)
        await self.wait(2)

        text = await self.get_text()
        # Parse trip blocks from page text
        import re
        trips = []
        for block in re.split(r"Voyage à ", text):
            if not block.strip() or "Voir le détail" not in block:
                continue
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            destination = lines[0] if lines else ""
            trip = {"destination": destination, "details": []}
            for line in lines[1:]:
                if line == "Voir le détail du voyage":
                    break
                trip["details"].append(line)
            trip["pro"] = "Pro" in trip["details"]
            trip["details"] = [d for d in trip["details"] if d != "Pro"]
            trips.append(trip)
        return trips

    async def request_justificatifs(self, email: str) -> Dict[str, Any]:
        """Select all past trips and send justificatifs to email."""
        await self._goto_trips("PASSED")

        # Click "Recevoir vos justificatifs d'achats"
        await self.evaluate("""
            [...document.querySelectorAll('span')].find(
                el => el.textContent.includes("justificatifs d'achats")
            )?.closest('button, a')?.click()
        """)
        await self.wait(3)

        # Select all
        await self.evaluate("""
            [...document.querySelectorAll('span, label, button')].find(
                el => el.textContent.trim() === 'Tout sélectionner'
            )?.click()
        """)
        await self.wait(1)

        # Click send by email
        await self.evaluate("""
            [...document.querySelectorAll('button, a')].find(
                el => el.textContent.includes('Recevoir par e-mail')
            )?.click()
        """)
        await self.wait(2)

        # Fill email
        await self.fill(
            "input[type='email'], input[placeholder*='mail']", email
        )
        await self.wait(1)

        # Submit
        await self.evaluate("""
            [...document.querySelectorAll('button')].find(
                el => el.textContent.includes('Recevoir le justificatif')
            )?.click()
        """)
        await self.wait(3)

        return {"status": "sent", "email": email}
