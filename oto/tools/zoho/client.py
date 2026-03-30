"""Zoho CRM API Client — https://www.zoho.com/crm/developer/docs/api/v7/"""

import json
import time
from pathlib import Path
from typing import Any, Optional

import requests

from ...config import require_secret, get_secret, get_cache_dir


class ZohoClient:
    API_VERSION = "v7"

    def __init__(self):
        self.client_id = require_secret("ZOHO_CLIENT_ID")
        self.client_secret = require_secret("ZOHO_CLIENT_SECRET")
        self.refresh_token = require_secret("ZOHO_REFRESH_TOKEN")
        self.api_domain = get_secret("ZOHO_API_DOMAIN", "https://www.zohoapis.com")
        self.accounts_url = get_secret("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com")
        self._token_path = get_cache_dir() / "zoho-access-token.json"

    # --- Auth ---

    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        # Try cached token
        if self._token_path.exists():
            data = json.loads(self._token_path.read_text())
            if data.get("expires_at", 0) > time.time() + 60:
                return data["access_token"]

        # Refresh
        resp = requests.post(
            f"{self.accounts_url}/oauth/v2/token",
            params={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
        )
        resp.raise_for_status()
        token_data = resp.json()

        if "error" in token_data:
            raise ValueError(f"Zoho OAuth error: {token_data['error']}")

        # Cache with expiry
        cache = {
            "access_token": token_data["access_token"],
            "expires_at": time.time() + token_data.get("expires_in", 3600),
        }
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(cache))
        return cache["access_token"]

    def _invalidate_token(self):
        """Remove cached token to force refresh on next request."""
        self._token_path.unlink(missing_ok=True)

    # --- HTTP ---

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.api_domain}/crm/{self.API_VERSION}/{endpoint}"
        token = self._get_access_token()
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}

        for attempt in range(3):
            resp = requests.request(method, url, headers=headers, **kwargs)

            # Token expired — refresh once and retry
            if resp.status_code == 401 and attempt == 0:
                self._invalidate_token()
                token = self._get_access_token()
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                continue

            # Rate limited
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2))
                time.sleep(wait)
                continue

            if resp.status_code >= 400:
                try:
                    error_body = resp.json()
                except Exception:
                    error_body = resp.text
                raise Exception(f"HTTP {resp.status_code}: {error_body}")

            return resp.json() if resp.content else {}

        raise Exception("Request failed after retries")

    # Default fields per module (avoids needing settings.fields scope)
    DEFAULT_FIELDS = {
        "Contacts": "First_Name,Last_Name,Email,Phone,Account_Name,Title",
        "Leads": "First_Name,Last_Name,Company,Email,Phone,Lead_Status",
        "Deals": "Deal_Name,Stage,Amount,Closing_Date,Account_Name,Contact_Name",
        "Accounts": "Account_Name,Website,Industry,Phone,Annual_Revenue",
        "Tasks": "Subject,Status,Due_Date,Priority,Owner",
        "Calls": "Subject,Call_Type,Call_Start_Time,Call_Duration,Owner",
        "Events": "Event_Title,Start_DateTime,End_DateTime,Location,Owner",
        "Campaigns": "Campaign_Name,Type,Status,Start_Date,End_Date",
        "Products": "Product_Name,Product_Code,Unit_Price,Qty_in_Stock",
        "Quotes": "Subject,Quote_Stage,Grand_Total,Valid_Till,Account_Name",
        "Invoices": "Subject,Status,Grand_Total,Due_Date,Account_Name",
    }

    # --- Modules ---

    def list_modules(self) -> list[dict]:
        """List available CRM modules."""
        data = self._request("GET", "settings/modules")
        return data.get("modules", [])

    # --- Records (generic CRUD) ---

    def list_records(
        self,
        module: str,
        page: int = 1,
        per_page: int = 200,
        fields: Optional[str] = None,
    ) -> dict:
        """List records from a module."""
        if not fields:
            fields = self.DEFAULT_FIELDS.get(module)
            if not fields:
                raise ValueError(
                    f"No default fields for module '{module}'. "
                    f"Pass --fields explicitly. Known modules: {', '.join(self.DEFAULT_FIELDS)}"
                )
        params: dict[str, Any] = {"page": page, "per_page": per_page, "fields": fields}
        return self._request("GET", module, params=params)

    def get_record(self, module: str, record_id: str) -> dict:
        """Get a single record."""
        data = self._request("GET", f"{module}/{record_id}")
        records = data.get("data", [])
        return records[0] if records else {}

    def search_records(
        self,
        module: str,
        criteria: str,
        page: int = 1,
        per_page: int = 200,
    ) -> dict:
        """Search records. criteria format: '(Field:operator:value)'."""
        params: dict[str, Any] = {
            "criteria": criteria,
            "page": page,
            "per_page": per_page,
        }
        return self._request("GET", f"{module}/search", params=params)

    def create_record(self, module: str, data: dict) -> dict:
        """Create a record."""
        body = {"data": [data]}
        return self._request("POST", module, json=body)

    def update_record(self, module: str, record_id: str, data: dict) -> dict:
        """Update a record."""
        body = {"data": [{"id": record_id, **data}]}
        return self._request("PUT", module, json=body)

    def delete_record(self, module: str, record_id: str) -> dict:
        """Delete a record."""
        return self._request("DELETE", f"{module}/{record_id}")

    # --- Notes ---

    def list_notes(self, module: str, record_id: str) -> list[dict]:
        """List notes for a record."""
        data = self._request("GET", f"{module}/{record_id}/Notes")
        return data.get("data", [])

    def create_note(self, module: str, record_id: str, title: str, content: str) -> dict:
        """Add a note to a record."""
        body = {"data": [{"Note_Title": title, "Note_Content": content}]}
        return self._request("POST", f"{module}/{record_id}/Notes", json=body)
