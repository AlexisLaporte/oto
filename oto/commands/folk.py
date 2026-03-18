"""Folk CRM commands."""

import json
import typer
from typing import Optional

app = typer.Typer(help="Folk CRM — contacts, companies, deals, notes")


def _out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _client():
    from oto.tools.folk import FolkClient
    return FolkClient()


# --- Groups ---

@app.command("groups")
def groups():
    """List all groups (pipelines)."""
    items = _client().list_groups()
    _out({"count": len(items), "groups": items})


# --- People ---

@app.command("people")
def people(
    search: Optional[str] = typer.Argument(None, help="Search by name"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Filter by group ID"),
):
    """List contacts."""
    c = _client()
    filters = {}
    if search:
        filters["fullName"] = search
    items = c.list_people(**filters)
    result = []
    for p in items:
        result.append({
            "id": p["id"],
            "name": p.get("fullName") or f"{p.get('firstName','')} {p.get('lastName','')}".strip(),
            "jobTitle": p.get("jobTitle", ""),
            "emails": p.get("emails", []),
            "companies": [co.get("name", "") for co in p.get("companies", [])],
        })
    _out({"count": len(result), "people": result})


@app.command("person")
def person(person_id: str = typer.Argument(..., help="Person ID (per_...)")):
    """Get a person's details."""
    _out(_client().get_person(person_id))


@app.command("add-person")
def add_person(
    first_name: str = typer.Argument(...),
    last_name: Optional[str] = typer.Option(None, "--last", "-l"),
    email: Optional[str] = typer.Option(None, "--email", "-e"),
    phone: Optional[str] = typer.Option(None, "--phone"),
    job_title: Optional[str] = typer.Option(None, "--title", "-t"),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Company name (creates if needed)"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Group ID"),
):
    """Create a contact."""
    emails = [email] if email else None
    phones = [phone] if phone else None
    group_ids = [group] if group else None
    result = _client().create_person(
        first_name=first_name, last_name=last_name,
        emails=emails, phones=phones, job_title=job_title,
        company_name=company, group_ids=group_ids,
    )
    _out(result)


@app.command("update-person")
def update_person(
    person_id: str = typer.Argument(..., help="Person ID (per_...)"),
    first_name: Optional[str] = typer.Option(None, "--first"),
    last_name: Optional[str] = typer.Option(None, "--last"),
    email: Optional[str] = typer.Option(None, "--email", "-e"),
    job_title: Optional[str] = typer.Option(None, "--title", "-t"),
    company: Optional[str] = typer.Option(None, "--company", "-c"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Set group (replaces all)"),
):
    """Update a contact."""
    fields = {}
    if first_name:
        fields["firstName"] = first_name
    if last_name:
        fields["lastName"] = last_name
    if email:
        fields["emails"] = [email]
    if job_title:
        fields["jobTitle"] = job_title
    if company:
        fields["companies"] = [{"name": company}]
    if group:
        fields["groups"] = [{"id": group}]
    _out(_client().update_person(person_id, **fields))


@app.command("delete-person")
def delete_person(person_id: str = typer.Argument(..., help="Person ID (per_...)")):
    """Delete a contact."""
    _client().delete_person(person_id)
    print(f"Deleted {person_id}")


# --- Companies ---

@app.command("companies")
def companies(search: Optional[str] = typer.Argument(None, help="Search by name")):
    """List companies."""
    filters = {}
    if search:
        filters["name"] = search
    items = _client().list_companies(**filters)
    _out({"count": len(items), "companies": items})


def _parse_fields(fields: Optional[list[str]]) -> dict:
    """Parse --field key=value pairs into a dict."""
    if not fields:
        return {}
    result = {}
    for f in fields:
        if "=" not in f:
            raise typer.BadParameter(f"Invalid field format: {f!r} (expected key=value)")
        key, value = f.split("=", 1)
        result[key] = value
    return result


@app.command("add-company")
def add_company(
    name: str = typer.Argument(...),
    industry: Optional[str] = typer.Option(None, "--industry", "-i"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Group ID"),
    fields: Optional[list[str]] = typer.Option(None, "--field", "-f", help="Custom field key=value (requires --group)"),
):
    """Create a company."""
    extra: dict = {}
    if group:
        extra["groups"] = [{"id": group}]
    custom = _parse_fields(fields)
    if custom:
        if not group:
            raise typer.BadParameter("--field requires --group")
        extra["customFieldValues"] = {group: custom}
    _out(_client().create_company(name=name, industry=industry, **extra))


@app.command("update-company")
def update_company(
    company_id: str = typer.Argument(..., help="Company ID (com_...)"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    industry: Optional[str] = typer.Option(None, "--industry", "-i"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Group ID"),
    fields: Optional[list[str]] = typer.Option(None, "--field", "-f", help="Custom field key=value (requires --group)"),
):
    """Update a company."""
    data: dict = {}
    if name:
        data["name"] = name
    if industry:
        data["industry"] = industry
    if group:
        data["groups"] = [{"id": group}]
    custom = _parse_fields(fields)
    if custom:
        if not group:
            raise typer.BadParameter("--field requires --group")
        data["customFieldValues"] = {group: custom}
    _out(_client().update_company(company_id, **data))


@app.command("delete-company")
def delete_company(company_id: str = typer.Argument(..., help="Company ID (com_...)")):
    """Delete a company."""
    _client().delete_company(company_id)
    print(f"Deleted {company_id}")


# --- Deals ---

@app.command("deals")
def deals(
    group: str = typer.Option(None, "--group", "-g", help="Group ID (default: first group)"),
    object_type: str = typer.Option("deals", "--type", "-t", help="Object type name"),
):
    """List deals in a pipeline group."""
    c = _client()
    if not group:
        groups = c.list_groups()
        if not groups:
            print("No groups found.")
            raise typer.Exit(1)
        group = groups[0]["id"]
    items = c.list_deals(group, object_type)
    _out({"count": len(items), "group": group, "deals": items})


# --- Notes ---

@app.command("notes")
def notes(entity_id: str = typer.Argument(..., help="Entity ID (per_/com_/obj_)")):
    """List notes for an entity."""
    items = _client().list_notes(entity_id)
    _out({"count": len(items), "notes": items})


@app.command("add-note")
def add_note(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    content: str = typer.Argument(..., help="Note content (markdown)"),
):
    """Add a note to a person/company/deal."""
    _out(_client().create_note(entity_id, content))


# --- Interactions ---

@app.command("add-interaction")
def add_interaction(
    entity_id: str = typer.Argument(..., help="Person or company ID"),
    type: str = typer.Argument(..., help="Type: call, meeting, email, linkedin, etc."),
    title: str = typer.Argument(..., help="Short title"),
    content: Optional[str] = typer.Option(None, "--content", "-c"),
    date: Optional[str] = typer.Option(None, "--date", "-d", help="ISO datetime"),
):
    """Log an interaction (call, meeting, email...)."""
    _out(_client().create_interaction(entity_id, type, title, content, date))
