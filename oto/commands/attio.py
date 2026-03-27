"""Attio CRM commands."""

import json
import typer
from typing import Optional

app = typer.Typer(help="Attio CRM — contacts, companies, deals, lists")


def _out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _client():
    from oto.tools.attio import AttioClient
    return AttioClient()


def _request(method, endpoint, **kwargs):
    """Direct API call for endpoints not covered by client."""
    c = _client()
    return c._request(method, endpoint, **kwargs)


def _query_all(object_type, limit=500):
    """Query all records of a type."""
    records = []
    offset = 0
    while True:
        data = _request("POST", f"objects/{object_type}/records/query", json={"limit": 50, "offset": offset})
        batch = data.get("data", [])
        records.extend(batch)
        if len(batch) < 50 or len(records) >= limit:
            break
        offset += 50
    return records


def _extract_value(values, slug):
    """Extract first value from Attio attribute values."""
    vals = values.get(slug, [])
    if not vals:
        return None
    v = vals[0]
    if isinstance(v, dict):
        # Handle different value types
        for key in ("value", "email_address", "phone_number", "full_name", "domain"):
            if key in v:
                return v[key]
        return v
    return v


# --- People ---

@app.command("people")
def people(search: Optional[str] = typer.Argument(None, help="Search by name")):
    """List contacts."""
    if search:
        data = _request("POST", "objects/people/records/query", json={
            "filter": {"name": {"$contains": search}},
            "limit": 50,
        })
        records = data.get("data", [])
    else:
        records = _query_all("people")

    result = []
    for r in records:
        v = r.get("values", {})
        name_val = v.get("name", [{}])
        name = name_val[0].get("full_name", "") if name_val else ""
        emails = [e.get("email_address", "") for e in v.get("email_addresses", [])]
        job = _extract_value(v, "job_title") or ""
        companies = []
        for co in v.get("company", []):
            co_name = co.get("target_record", {}).get("values", {}).get("name", [{}])
            if co_name:
                companies.append(co_name[0].get("value", ""))
        result.append({
            "id": r["id"]["record_id"],
            "name": name,
            "jobTitle": job,
            "emails": emails,
            "companies": companies,
        })
    _out({"count": len(result), "people": result})


@app.command("person")
def person(record_id: str = typer.Argument(..., help="Record ID")):
    """Get a person's details."""
    data = _request("GET", f"objects/people/records/{record_id}")
    _out(data.get("data", {}))


@app.command("add-person")
def add_person(
    first_name: str = typer.Argument(...),
    last_name: Optional[str] = typer.Option(None, "--last", "-l"),
    email: Optional[str] = typer.Option(None, "--email", "-e"),
    phone: Optional[str] = typer.Option(None, "--phone"),
    job_title: Optional[str] = typer.Option(None, "--title", "-t"),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Company name (matches existing)"),
    linkedin: Optional[str] = typer.Option(None, "--linkedin", help="LinkedIn URL"),
):
    """Create a contact."""
    values = {}
    full = f"{first_name} {last_name}".strip() if last_name else first_name
    values["name"] = [{"first_name": first_name, "last_name": last_name or "", "full_name": full}]
    if email:
        values["email_addresses"] = [{"email_address": email}]
    if phone:
        values["phone_numbers"] = [{"phone_number": phone}]
    if job_title:
        values["job_title"] = [{"value": job_title}]
    if linkedin:
        values["linkedin"] = [{"value": linkedin}]
    if company:
        # Search for company by name
        co_data = _request("POST", "objects/companies/records/query", json={
            "filter": {"name": {"$eq": company}},
            "limit": 1,
        })
        co_records = co_data.get("data", [])
        if co_records:
            values["company"] = [{"target_object": "companies", "target_record_id": co_records[0]["id"]["record_id"]}]

    result = _request("POST", "objects/people/records", json={"data": {"values": values}})
    _out(result.get("data", {}))


@app.command("delete-person")
def delete_person(record_id: str = typer.Argument(..., help="Record ID")):
    """Delete a contact."""
    _request("DELETE", f"objects/people/records/{record_id}")
    print(f"Deleted {record_id}")


# --- Companies ---

@app.command("companies")
def companies(search: Optional[str] = typer.Argument(None, help="Search by name")):
    """List companies."""
    if search:
        data = _request("POST", "objects/companies/records/query", json={
            "filter": {"name": {"$contains": search}},
            "limit": 50,
        })
        records = data.get("data", [])
    else:
        records = _query_all("companies")

    result = []
    for r in records:
        v = r.get("values", {})
        result.append({
            "id": r["id"]["record_id"],
            "name": _extract_value(v, "name") or "",
            "domain": _extract_value(v, "domains") or "",
            "description": _extract_value(v, "description") or "",
        })
    _out({"count": len(result), "companies": result})


@app.command("add-company")
def add_company(
    name: str = typer.Argument(...),
    domain: Optional[str] = typer.Option(None, "--domain", "-d"),
    description: Optional[str] = typer.Option(None, "--desc"),
):
    """Create a company."""
    values = {"name": [{"value": name}]}
    if domain:
        values["domains"] = [{"domain": domain}]
    if description:
        values["description"] = [{"value": description}]
    result = _request("POST", "objects/companies/records", json={"data": {"values": values}})
    _out(result.get("data", {}))


@app.command("delete-company")
def delete_company(record_id: str = typer.Argument(..., help="Record ID")):
    """Delete a company."""
    _request("DELETE", f"objects/companies/records/{record_id}")
    print(f"Deleted {record_id}")


# --- Lists ---

@app.command("lists")
def lists():
    """List all lists (pipelines)."""
    data = _request("GET", "lists")
    items = data.get("data", [])
    _out({"count": len(items), "lists": [
        {"id": l["id"]["list_id"], "name": l["name"], "slug": l.get("api_slug", "")}
        for l in items
    ]})


@app.command("list-entries")
def list_entries(
    list_slug: str = typer.Argument(..., help="List slug (clients, leads, partners, culture)"),
):
    """List entries in a list."""
    data = _request("POST", f"lists/{list_slug}/entries/query", json={"limit": 100})
    entries = data.get("data", [])
    result = []
    for e in entries:
        result.append({
            "entry_id": e["id"]["entry_id"],
            "record_id": e.get("parent_record_id", ""),
        })
    _out({"count": len(result), "list": list_slug, "entries": result})


@app.command("add-entry")
def add_entry(
    list_slug: str = typer.Argument(..., help="List slug (clients, leads, partners, culture)"),
    record_id: str = typer.Argument(..., help="Record ID (company or person)"),
    parent_object: str = typer.Option("companies", "--type", "-t", help="Parent object type: companies or people"),
):
    """Add a record to a list."""
    result = _request("POST", f"lists/{list_slug}/entries", json={
        "data": {
            "parent_record_id": record_id,
            "parent_object": parent_object,
            "entry_values": {},
        },
    })
    entry = result.get("data", {})
    _out({"entry_id": entry.get("id", {}).get("entry_id", ""), "record_id": record_id, "list": list_slug})


# --- Notes ---

@app.command("add-note")
def add_note(
    record_id: str = typer.Argument(..., help="Record ID"),
    title: str = typer.Argument(..., help="Note title"),
    content: str = typer.Argument(..., help="Note content (markdown)"),
    object_type: str = typer.Option("people", "--type", "-t", help="Object type: people or companies"),
):
    """Add a note to a person or company."""
    result = _client().notes.create(object_type, record_id, title, content)
    _out(result)
