"""
Notion API client with caching support.
"""
import json
import hashlib
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
import requests

from ....config import get_cache_dir


class NotionClient:
    """Notion API client with automatic caching."""

    def __init__(self, token: Optional[str] = None):
        """Initialize Notion client.

        Args:
            token: Notion integration token. If not provided, reads from .keys/notion-token.txt
        """
        self.base_url = "https://api.notion.com/v1"
        self.token = token or self._load_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json"
        }

        # Setup cache directory
        self.cache_dir = get_cache_dir() / 'notion'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = 86400  # 24 hours

    def _load_token(self) -> str:
        """Load Notion token from config."""
        from oto.config import require_secret
        return require_secret('NOTION_API_KEY')

    def _get_cache_key(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> str:
        """Generate cache key from request parameters."""
        cache_data = {
            'method': method,
            'endpoint': endpoint,
            'params': params or {},
            'data': data or {}
        }
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_string.encode()).hexdigest()

    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Get cached response if valid."""
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        # Check TTL
        file_age = time.time() - cache_file.stat().st_mtime
        if file_age > self.cache_ttl:
            cache_file.unlink()  # Remove expired cache
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _set_cache(self, cache_key: str, data: Dict):
        """Save response to cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to cache response: {e}")

    def _request(self, method: str, endpoint: str, params: Dict = None,
                 data: Dict = None, use_cache: bool = True) -> Dict:
        """Make API request with caching."""

        # Check cache for GET requests
        if use_cache and method == 'GET':
            cache_key = self._get_cache_key(method, endpoint, params, data)
            cached = self._get_cached(cache_key)
            if cached:
                print(f"✓ Using cached response (age: {int(time.time() - (self.cache_dir / f'{cache_key}.json').stat().st_mtime)}s)")
                return cached

        # Make API request
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=data
            )
            response.raise_for_status()
            result = response.json()

            # Cache GET requests
            if use_cache and method == 'GET':
                cache_key = self._get_cache_key(method, endpoint, params, data)
                self._set_cache(cache_key, result)

            return result

        except requests.exceptions.HTTPError as e:
            error_data = e.response.json() if e.response.text else {}
            error_msg = error_data.get('message', str(e))
            error_code = error_data.get('code', '')
            status_code = e.response.status_code

            # Enhanced error messages based on status code
            if status_code == 404:
                raise Exception(
                    f"Notion API error (404): Resource not found.\n"
                    f"  Endpoint: {endpoint}\n"
                    f"  Message: {error_msg}\n"
                    f"  Possible causes:\n"
                    f"  - Invalid ID (database/page does not exist)\n"
                    f"  - Integration lacks access permissions to this resource\n"
                    f"  - Resource is in trash or archived"
                )
            elif status_code == 403:
                raise Exception(
                    f"Notion API error (403): Forbidden.\n"
                    f"  Message: {error_msg}\n"
                    f"  The integration does not have permission to access this resource.\n"
                    f"  Add the integration to the page/database in Notion."
                )
            elif status_code == 401:
                raise Exception(
                    f"Notion API error (401): Unauthorized.\n"
                    f"  Message: {error_msg}\n"
                    f"  Check that your Notion integration token is valid."
                )
            elif status_code == 400:
                raise Exception(
                    f"Notion API error (400): Bad request.\n"
                    f"  Message: {error_msg}\n"
                    f"  Code: {error_code}\n"
                    f"  Check the request parameters."
                )
            else:
                raise Exception(
                    f"Notion API error ({status_code}): {error_msg}\n"
                    f"  Code: {error_code}"
                )
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    # API Methods

    def search(self, query: str, filter_type: Optional[str] = None,
               sort: str = "relevance") -> Dict:
        """Search Notion workspace."""
        data = {"query": query}

        # Only add sort if not relevance (Notion API default)
        if sort != "relevance":
            data["sort"] = {"direction": "descending", "timestamp": sort}

        if filter_type:
            data["filter"] = {"value": filter_type, "property": "object"}

        return self._request('POST', 'search', data=data, use_cache=True)

    def get_page(self, page_id: str) -> Dict:
        """Get page metadata."""
        page_id = page_id.replace('-', '')
        return self._request('GET', f'pages/{page_id}')

    def get_page_blocks(self, page_id: str, recursive: bool = False) -> Dict:
        """Get page blocks (content).

        Args:
            page_id: Page or block ID
            recursive: If True, fetch children of blocks recursively
        """
        page_id = page_id.replace('-', '')
        result = self._request('GET', f'blocks/{page_id}/children')

        if recursive and 'results' in result:
            for block in result['results']:
                if block.get('has_children'):
                    block_id = block['id'].replace('-', '')
                    children = self.get_page_blocks(block_id, recursive=True)
                    block['children'] = children.get('results', [])

        return result

    def get_block_children(self, block_id: str, recursive: bool = False) -> Dict:
        """Get children of a specific block.

        Args:
            block_id: Block ID
            recursive: If True, fetch children recursively
        """
        return self.get_page_blocks(block_id, recursive=recursive)

    def query_data_source(self, data_source_id: str, filter_obj: Optional[Dict] = None,
                          sorts: Optional[list] = None, page_size: int = 100) -> Dict:
        """Query data source (Notion API 2025-09-03)."""
        data_source_id = data_source_id.replace('-', '')
        data = {"page_size": page_size}

        if filter_obj:
            data["filter"] = filter_obj
        if sorts:
            data["sorts"] = sorts

        return self._request('POST', f'data_sources/{data_source_id}/query', data=data)

    def query_database(self, database_id: str, filter_obj: Optional[Dict] = None,
                       sorts: Optional[list] = None, page_size: int = 100) -> Dict:
        """Query database by finding its data source and querying that.

        In Notion API 2025-09-03, databases must be queried via their data_sources.
        This method automatically retrieves the database's data source and queries it.
        """
        database_id = database_id.replace('-', '')

        try:
            # Get database to find data sources
            db_info = self.get_database(database_id)
            data_sources = db_info.get('data_sources', [])

            if not data_sources:
                raise Exception(
                    f"Database {database_id} has no data sources.\n"
                    f"This may be an empty database or a permissions issue."
                )

            # Use the first data source (most common case)
            data_source_id = data_sources[0]['id']

            # Query the data source
            return self.query_data_source(data_source_id, filter_obj, sorts, page_size)

        except Exception as e:
            error_str = str(e)
            if 'invalid_request_url' in error_str.lower():
                raise Exception(
                    f"Cannot query database {database_id}.\n"
                    f"Original error: {error_str}\n\n"
                    f"This error occurs when using API version 2025-09-03 with the old endpoint.\n"
                    f"The tool has been updated to use data sources, but this error persists.\n"
                    f"Please verify the database has data sources and your integration has access."
                )
            raise

    def get_database(self, database_id: str) -> Dict:
        """Get database metadata and schema."""
        database_id = database_id.replace('-', '')
        return self._request('GET', f'databases/{database_id}')

    def create_page(self, parent_id: str, parent_type: str,
                    title: str, properties: Optional[Dict] = None,
                    content: Optional[list] = None) -> Dict:
        """Create new page."""
        parent_id = parent_id.replace('-', '')

        data = {
            "parent": {
                f"{parent_type}_id": parent_id
            },
            "properties": {}
        }

        # Set title
        if parent_type == "database":
            data["properties"]["Name"] = {
                "title": [{"text": {"content": title}}]
            }
        else:
            data["properties"]["title"] = {
                "title": [{"text": {"content": title}}]
            }

        # Add custom properties
        if properties:
            data["properties"].update(properties)

        # Add content blocks
        if content:
            data["children"] = content

        return self._request('POST', 'pages', data=data, use_cache=False)

    def update_page(self, page_id: str, properties: Optional[Dict] = None,
                    archived: Optional[bool] = None) -> Dict:
        """Update page properties."""
        page_id = page_id.replace('-', '')
        data = {}

        if properties:
            data["properties"] = properties
        if archived is not None:
            data["archived"] = archived

        return self._request('PATCH', f'pages/{page_id}', data=data, use_cache=False)

    def append_blocks(self, page_id: str, blocks: list) -> Dict:
        """Append blocks to page."""
        page_id = page_id.replace('-', '')
        data = {"children": blocks}
        return self._request('PATCH', f'blocks/{page_id}/children', data=data, use_cache=False)
