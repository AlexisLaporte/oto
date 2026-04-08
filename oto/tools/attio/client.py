"""
Attio CRM API Client.

Requires: requests
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

import requests

from ...config import require_secret


@dataclass
class Company:
    """Company record."""
    id: str
    name: str
    domain: str = None
    industry: str = None
    employee_count: int = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Person:
    """Person record."""
    id: str
    name: str
    email: str = None
    phone: str = None
    company_id: str = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Deal:
    """Deal record."""
    id: str
    name: str
    value: float = None
    stage: str = None
    company_id: str = None
    attributes: Dict[str, Any] = field(default_factory=dict)


class AttioResource:
    """Base class for Attio resources."""

    def __init__(self, client: "AttioClient", object_type: str):
        self.client = client
        self.object_type = object_type

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        sort: str = None,
    ) -> List[Dict[str, Any]]:
        """List records."""
        params = {"limit": limit, "offset": offset}
        if sort:
            params["sort"] = sort

        return self.client._request("GET", f"objects/{self.object_type}/records", params=params)

    def get(self, record_id: str) -> Dict[str, Any]:
        """Get a specific record."""
        return self.client._request("GET", f"objects/{self.object_type}/records/{record_id}")

    def create(self, **attributes) -> Dict[str, Any]:
        """Create a new record."""
        data = {"data": {"values": attributes}}
        return self.client._request("POST", f"objects/{self.object_type}/records", json=data)

    def update(self, record_id: str, **attributes) -> Dict[str, Any]:
        """Update a record."""
        data = {"data": {"values": attributes}}
        return self.client._request("PATCH", f"objects/{self.object_type}/records/{record_id}", json=data)

    def delete(self, record_id: str) -> Dict[str, Any]:
        """Delete a record."""
        return self.client._request("DELETE", f"objects/{self.object_type}/records/{record_id}")

    def search(
        self,
        query: str = None,
        filters: List[Dict] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search records."""
        data = {"limit": limit}
        if query:
            data["query"] = query
        if filters:
            data["filters"] = filters

        return self.client._request("POST", f"objects/{self.object_type}/records/query", json=data)


class AttioNotes:
    """Notes resource."""

    def __init__(self, client: "AttioClient"):
        self.client = client

    def create(
        self,
        parent_object: str,
        parent_record_id: str,
        title: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Create a note.

        Args:
            parent_object: Object type (companies, people, deals)
            parent_record_id: Record ID to attach note to
            title: Note title
            content: Note content (markdown)

        Returns:
            Created note
        """
        data = {
            "data": {
                "parent_object": parent_object,
                "parent_record_id": parent_record_id,
                "title": title,
                "format": "markdown",
                "content": content,
            }
        }
        return self.client._request("POST", "notes", json=data)

    def list(self, parent_object: str = None, parent_record_id: str = None) -> List[Dict[str, Any]]:
        """List notes."""
        params = {}
        if parent_object:
            params["parent_object"] = parent_object
        if parent_record_id:
            params["parent_record_id"] = parent_record_id

        return self.client._request("GET", "notes", params=params)


class AttioTasks:
    """Tasks resource."""

    def __init__(self, client: "AttioClient"):
        self.client = client

    def _get_default_assignee(self) -> str:
        """Get first workspace member ID as default assignee."""
        data = self.client._request("GET", "workspace_members")
        members = data.get("data", [])
        if not members:
            raise Exception("No workspace members found")
        return members[0]["id"]["workspace_member_id"]

    def create(
        self,
        content: str,
        deadline: str = None,
        assignee_id: str = None,
        linked_object: str = None,
        linked_record_id: str = None,
    ) -> Dict[str, Any]:
        """
        Create a task.

        Args:
            content: Task description (max 2000 chars)
            deadline: ISO date or YYYY-MM-DD deadline
            assignee_id: Workspace member ID (defaults to first member)
            linked_object: Object type to link (companies, people)
            linked_record_id: Record ID to link

        Returns:
            Created task
        """
        if not assignee_id:
            assignee_id = self._get_default_assignee()

        task_data = {
            "content": content,
            "format": "plaintext",
            "is_completed": False,
            "assignees": [{"referenced_actor_type": "workspace-member", "referenced_actor_id": assignee_id}],
        }
        if deadline:
            if len(deadline) == 10:  # YYYY-MM-DD
                deadline = f"{deadline}T00:00:00.000Z"
            task_data["deadline_at"] = deadline
        if linked_object and linked_record_id:
            task_data["linked_records"] = [{
                "target_object": linked_object,
                "target_record_id": linked_record_id,
            }]

        return self.client._request("POST", "tasks", json={"data": task_data})

    def list(self, completed: bool = None) -> List[Dict[str, Any]]:
        """List tasks."""
        params = {}
        if completed is not None:
            params["completed"] = completed

        return self.client._request("GET", "tasks", params=params)


class AttioClient:
    """
    Attio CRM API client.

    Usage:
        client = AttioClient()
        companies = client.companies.list()
        client.companies.create(name="Acme Inc", domain="acme.com")
    """

    BASE_URL = "https://api.attio.com/v2"

    def __init__(self, api_key: str = None):
        """
        Initialize Attio client.

        Args:
            api_key: Attio API key (or set ATTIO_API_KEY env var)
        """
        self.api_key = api_key or require_secret("ATTIO_API_KEY")

        # Initialize resources
        self.companies = AttioResource(self, "companies")
        self.people = AttioResource(self, "people")
        self.deals = AttioResource(self, "deals")
        self.notes = AttioNotes(self)
        self.tasks = AttioTasks(self)

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make API request."""
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code == 429:
            raise Exception("Rate limit exceeded")

        response.raise_for_status()

        if response.content:
            return response.json()
        return {}
