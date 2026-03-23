"""
Pennylane API Client - Fetch accounting data from Pennylane.

Requires: requests

Usage:
    client = PennylaneClient(api_key="your-api-key")

    # Get company info
    me = client.fetch("me")

    # Get trial balance for a year
    trial = client.fetch("trial_balance", {
        'period_start': '2025-01-01',
        'period_end': '2025-12-31'
    })

    # Fetch all pages of ledger accounts
    accounts = client.fetch_all_pages("ledger_accounts")
"""

import time
from typing import Optional

import requests

from ...config import require_secret


class PennylaneClient:
    """Client for Pennylane API v2"""

    BASE_URL = "https://app.pennylane.com/api/external/v2"

    def __init__(self, api_key: str = None, rate_limit_delay: float = 0.3):
        """
        Initialize the Pennylane client.

        Args:
            api_key: Pennylane API bearer token (or set PENNYLANE_API_KEY env var)
            rate_limit_delay: Delay between requests (default 0.3s for 4 req/sec limit)
        """
        self.api_key = api_key or require_secret("PENNYLANE_API_KEY")
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def post(self, endpoint: str, data: dict, retries: int = 3) -> dict:
        """POST data to Pennylane API with retry on rate limit."""
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.post(url, json=data, timeout=30)

                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue

                if not response.ok:
                    return {
                        "error": str(response.status_code),
                        "details": response.text,
                        "status_code": response.status_code,
                    }

                if response.status_code == 204 or not response.content:
                    return {"ok": True}

                return response.json()
            except Exception as e:
                return {"error": str(e)}

        return {"error": "Max retries exceeded"}

    def put(self, endpoint: str, data: dict, retries: int = 3) -> dict:
        """PUT data to Pennylane API with retry on rate limit."""
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.put(url, json=data, timeout=30)

                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue

                if not response.ok:
                    return {
                        "error": str(response.status_code),
                        "details": response.text,
                        "status_code": response.status_code,
                    }

                return response.json()
            except Exception as e:
                return {"error": str(e)}

        return {"error": "Max retries exceeded"}

    def fetch(self, endpoint: str, params: Optional[dict] = None, retries: int = 3) -> dict:
        """
        Fetch data from Pennylane API with retry on rate limit.

        Args:
            endpoint: API endpoint (e.g., "me", "trial_balance", "ledger_accounts")
            params: Optional query parameters
            retries: Number of retries on rate limit

        Returns:
            JSON response as dict
        """
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue

                if not response.ok:
                    return {
                        "error": str(response.status_code),
                        "details": response.text,
                        "status_code": response.status_code,
                    }

                return response.json()
            except Exception as e:
                return {"error": str(e)}

        return {"error": "Max retries exceeded"}

    def fetch_all_pages(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_pages: Optional[int] = None,
        per_page: int = 100
    ) -> list:
        """
        Fetch all pages of a paginated endpoint.
        Supports both page-based and cursor-based pagination.
        """
        all_data = []
        if params is None:
            params = {}
        params['per_page'] = per_page
        page = 1
        cursor = None

        while True:
            if cursor:
                params['cursor'] = cursor
                params.pop('page', None)
            else:
                params['page'] = page

            data = self.fetch(endpoint, params)
            time.sleep(self.rate_limit_delay)

            if 'error' in data:
                break

            # Handle different response formats
            if 'items' in data:
                items = data['items']
                has_more = data.get('has_more', False)
                next_cursor = data.get('next_cursor')
                total_pages = data.get('total_pages', 1)
            elif 'data' in data:
                items = data['data']
                has_more = False
                next_cursor = None
                total_pages = data.get('pagination', {}).get('total_pages', 1)
            else:
                return data if isinstance(data, list) else [data]

            if not items:
                break

            all_data.extend(items)

            # Cursor-based pagination
            if next_cursor and has_more:
                cursor = next_cursor
            elif has_more:
                page += 1
            elif page < total_pages:
                page += 1
            else:
                break

            if max_pages and page > max_pages:
                break

        return all_data

    def get_company_info(self) -> dict:
        """Get company information."""
        return self.fetch("me")

    def get_fiscal_years(self) -> list:
        """Get fiscal years."""
        return self.fetch("fiscal_years")

    def get_trial_balance(self, start_date: str, end_date: str) -> list:
        """
        Get trial balance for a period.

        Args:
            start_date: Period start (YYYY-MM-DD)
            end_date: Period end (YYYY-MM-DD)
        """
        return self.fetch_all_pages("trial_balance", {
            'period_start': start_date,
            'period_end': end_date
        })

    def get_ledger_accounts(self) -> list:
        """Get all ledger accounts."""
        return self.fetch_all_pages("ledger_accounts")

    def get_ledger_entries(self, max_pages: Optional[int] = None) -> list:
        """Get ledger entries."""
        return self.fetch_all_pages("ledger_entries", max_pages=max_pages)

    def get_customer_invoices(self, max_pages: Optional[int] = None) -> list:
        """Get customer invoices."""
        return self.fetch_all_pages("customer_invoices", max_pages=max_pages)

    def get_supplier_invoices(self, max_pages: Optional[int] = None) -> list:
        """Get supplier invoices."""
        return self.fetch_all_pages("supplier_invoices", max_pages=max_pages)

    def get_categories(self) -> list:
        """Get expense categories."""
        return self.fetch("categories")

    def get_transactions(self, max_pages: Optional[int] = None) -> list:
        """Get bank transactions."""
        return self.fetch_all_pages("transactions", max_pages=max_pages)

    # --- File Attachments ---

    def upload_file(self, file_path: str) -> dict:
        """Upload a file (PDF) to Pennylane. Returns dict with id, filename, url."""
        import os
        url = f"{self.BASE_URL}/file_attachments"
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            response = self.session.post(
                url,
                files={"file": (filename, f, "application/pdf")},
                timeout=60,
            )
        if not response.ok:
            return {
                "error": str(response.status_code),
                "details": response.text,
                "status_code": response.status_code,
            }
        return response.json()

    # --- Customers ---

    def list_customers(self, max_pages: Optional[int] = None) -> list:
        """List all customers."""
        return self.fetch_all_pages("company_customers", max_pages=max_pages)

    def create_customer(self, name: str, emails: list[str] = None,
                        address: str = None, postal_code: str = None,
                        city: str = None, country_alpha2: str = "FR",
                        external_reference: str = None) -> dict:
        """Create a customer."""
        body = {"name": name}
        if emails:
            body["emails"] = emails
        if address or postal_code or city:
            body["billing_address"] = {
                k: v for k, v in {
                    "address": address, "postal_code": postal_code,
                    "city": city, "country_alpha2": country_alpha2,
                }.items() if v
            }
        if external_reference:
            body["external_reference"] = external_reference
        return self.post("company_customers", body)

    # --- Products ---

    def list_products(self, max_pages: Optional[int] = None) -> list:
        """List all products."""
        return self.fetch_all_pages("products", max_pages=max_pages)

    def create_product(self, label: str, unit_price: str, unit: str = "day",
                       vat_rate: str = "FR_200", description: str = None) -> dict:
        """Create a product. unit_price as string (e.g. '700.00')."""
        body = {
            "label": label,
            "price_before_tax": unit_price,
            "unit": unit,
            "vat_rate": vat_rate,
        }
        if description:
            body["description"] = description
        return self.post("products", body)

    # --- Customer Invoices ---

    def create_customer_invoice(self, customer_id: int, date: str, deadline: str,
                                lines: list[dict], draft: bool = True,
                                external_reference: str = None,
                                currency: str = "EUR") -> dict:
        """
        Create a customer invoice.

        lines: list of dicts with keys: product_id, quantity, and optionally
               label, raw_currency_unit_price, unit, vat_rate.
        """
        body = {
            "customer_id": customer_id,
            "date": date,
            "deadline": deadline,
            "draft": draft,
            "currency": currency,
            "invoice_lines": lines,
        }
        if external_reference:
            body["external_reference"] = external_reference
        return self.post("customer_invoices", body)

    def finalize_invoice(self, invoice_id: int) -> dict:
        """Finalize a draft invoice."""
        return self.put(f"customer_invoices/{invoice_id}/finalize", {})

    # --- Quotes ---

    def create_quote(self, customer_id: int, date: str, deadline: str,
                     lines: list[dict], external_reference: str = None,
                     currency: str = "EUR", language: str = "fr") -> dict:
        """Create a quote."""
        body = {
            "customer_id": customer_id,
            "date": date,
            "deadline": deadline,
            "currency": currency,
            "language": language,
            "invoice_lines": lines,
        }
        if external_reference:
            body["external_reference"] = external_reference
        return self.post("quotes", body)

    # --- Aggregates ---

    def fetch_complete_data(self, year: int = 2025) -> dict:
        """
        Fetch complete financial data for a year.

        Args:
            year: Fiscal year to fetch

        Returns:
            Dict with all financial data
        """
        data = {
            'company': self.get_company_info(),
            'fiscal_years': self.get_fiscal_years(),
            'ledger_accounts': self.get_ledger_accounts(),
            f'trial_balance_{year}': self.get_trial_balance(
                f'{year}-01-01', f'{year}-12-31'
            ),
            'customer_invoices': self.get_customer_invoices(max_pages=50),
            'supplier_invoices': self.get_supplier_invoices(max_pages=50),
            'categories': self.get_categories(),
        }
        return data
