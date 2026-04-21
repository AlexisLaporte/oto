"""Attio CRM commands."""

import json
import typer
from typing import Optional

app = typer.Typer(help="Attio CRM — contacts, companies, deals, lists")

# Task subcommands
task_app = typer.Typer(help="Tasks (reminders, follow-ups)")
app.add_typer(task_app, name="task")


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


# --- Deals ---

# Required: owner. Defaults to first workspace member (Alexis).
def _default_owner():
    data = _request("GET", "workspace_members")
    members = data.get("data", [])
    if not members:
        raise Exception("No workspace members found")
    return members[0]["id"]["workspace_member_id"]


@app.command("deals")
def deals(
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter by stage title"),
):
    """List deals."""
    filt = {}
    if stage:
        filt["stage"] = {"$eq": stage}
    payload = {"limit": 200}
    if filt:
        payload["filter"] = filt
    data = _request("POST", "objects/deals/records/query", json=payload)
    records = data.get("data", [])
    result = []
    for r in records:
        v = r.get("values", {})
        name = _extract_value(v, "name") or ""
        slug = _extract_value(v, "slug") or ""
        st = ""
        stage_vals = v.get("stage", [])
        if stage_vals:
            st = stage_vals[0].get("status", {}).get("title", "")
        tjm_vals = v.get("tjm", [])
        tjm = tjm_vals[0].get("currency_value") if tjm_vals else None
        result.append({
            "id": r["id"]["record_id"],
            "slug": slug,
            "name": name,
            "stage": st,
            "tjm": tjm,
        })
    _out({"count": len(result), "deals": result})


@app.command("deal")
def deal(record_id: str = typer.Argument(..., help="Record ID or slug")):
    """Get a deal's details (by record_id or slug)."""
    # Try slug first if it doesn't look like a UUID
    if "-" in record_id and len(record_id) != 36:
        data = _request("POST", "objects/deals/records/query", json={
            "filter": {"slug": {"$eq": record_id}}, "limit": 1,
        })
        records = data.get("data", [])
        if not records:
            print(f"No deal with slug '{record_id}'")
            raise typer.Exit(1)
        record_id = records[0]["id"]["record_id"]
    data = _request("GET", f"objects/deals/records/{record_id}")
    _out(data.get("data", {}))


@app.command("add-deal")
def add_deal(
    slug: str = typer.Argument(..., help="Mission slug (FS folder name)"),
    name: str = typer.Argument(..., help="Deal name (e.g. 'client — objet')"),
    stage: str = typer.Option("Lead", "--stage", "-s", help="Stage title: Lead, In Discussion, Proposal, Active, Won 🎉, Lost"),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Company name (matches existing)"),
    people: Optional[str] = typer.Option(None, "--people", "-p", help="Comma-separated person names"),
    tjm: Optional[float] = typer.Option(None, "--tjm", help="TJM en EUR"),
    via: Optional[str] = typer.Option(None, "--via", help="Intermédiaire (ex. Patrick Amiel 321founded)"),
    debut: Optional[str] = typer.Option(None, "--debut", help="Date début YYYY-MM-DD"),
    fin: Optional[str] = typer.Option(None, "--fin", help="Date fin YYYY-MM-DD"),
    customer_id: Optional[int] = typer.Option(None, "--pennylane-customer", help="Pennylane customer ID"),
    product_id: Optional[int] = typer.Option(None, "--pennylane-product", help="Pennylane product ID"),
):
    """Create a deal."""
    values = {
        "name": [{"value": name}],
        "slug": [{"value": slug}],
        "stage": [{"status": stage}],
        "owner": [{
            "referenced_actor_type": "workspace-member",
            "referenced_actor_id": _default_owner(),
        }],
    }
    if company:
        co = _request("POST", "objects/companies/records/query", json={
            "filter": {"name": {"$eq": company}}, "limit": 1,
        }).get("data", [])
        if co:
            values["associated_company"] = [{
                "target_object": "companies",
                "target_record_id": co[0]["id"]["record_id"],
            }]
        else:
            print(f"WARN: company '{company}' not found")
    if people:
        person_refs = []
        for pname in [p.strip() for p in people.split(",") if p.strip()]:
            ppl = _request("POST", "objects/people/records/query", json={
                "filter": {"name": {"$contains": pname}}, "limit": 1,
            }).get("data", [])
            if ppl:
                person_refs.append({
                    "target_object": "people",
                    "target_record_id": ppl[0]["id"]["record_id"],
                })
            else:
                print(f"WARN: person '{pname}' not found")
        if person_refs:
            values["associated_people"] = person_refs
    if tjm is not None:
        values["tjm"] = float(tjm)
    if via:
        values["via"] = [{"value": via}]
    if debut:
        values["debut"] = [{"value": debut}]
    if fin:
        values["fin"] = [{"value": fin}]
    if customer_id is not None:
        values["pennylane_customer_id"] = [{"value": int(customer_id)}]
    if product_id is not None:
        values["pennylane_product_id"] = [{"value": int(product_id)}]

    result = _request("POST", "objects/deals/records", json={"data": {"values": values}})
    _out(result.get("data", {}))


@app.command("update-deal")
def update_deal(
    record_id: str = typer.Argument(..., help="Record ID or slug"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="New stage title"),
    tjm: Optional[float] = typer.Option(None, "--tjm"),
    via: Optional[str] = typer.Option(None, "--via"),
    debut: Optional[str] = typer.Option(None, "--debut"),
    fin: Optional[str] = typer.Option(None, "--fin"),
    customer_id: Optional[int] = typer.Option(None, "--pennylane-customer"),
    product_id: Optional[int] = typer.Option(None, "--pennylane-product"),
):
    """Update a deal (by record_id or slug)."""
    # Resolve slug -> record_id
    if "-" in record_id and len(record_id) != 36:
        data = _request("POST", "objects/deals/records/query", json={
            "filter": {"slug": {"$eq": record_id}}, "limit": 1,
        })
        records = data.get("data", [])
        if not records:
            print(f"No deal with slug '{record_id}'")
            raise typer.Exit(1)
        record_id = records[0]["id"]["record_id"]

    values = {}
    if stage:
        values["stage"] = [{"status": stage}]
    if tjm is not None:
        values["tjm"] = float(tjm)
    if via is not None:
        values["via"] = [{"value": via}]
    if debut is not None:
        values["debut"] = [{"value": debut}]
    if fin is not None:
        values["fin"] = [{"value": fin}]
    if customer_id is not None:
        values["pennylane_customer_id"] = [{"value": int(customer_id)}]
    if product_id is not None:
        values["pennylane_product_id"] = [{"value": int(product_id)}]

    if not values:
        print("Nothing to update")
        return
    result = _request("PATCH", f"objects/deals/records/{record_id}", json={"data": {"values": values}})
    _out(result.get("data", {}))


@app.command("delete-deal")
def delete_deal(record_id: str = typer.Argument(..., help="Record ID or slug")):
    """Delete a deal."""
    if "-" in record_id and len(record_id) != 36:
        data = _request("POST", "objects/deals/records/query", json={
            "filter": {"slug": {"$eq": record_id}}, "limit": 1,
        })
        records = data.get("data", [])
        if not records:
            print(f"No deal with slug '{record_id}'")
            raise typer.Exit(1)
        record_id = records[0]["id"]["record_id"]
    _request("DELETE", f"objects/deals/records/{record_id}")
    print(f"Deleted {record_id}")


# --- Notes ---

@app.command("add-note")
def add_note(
    record_id: str = typer.Argument(..., help="Record ID"),
    title: str = typer.Argument(..., help="Note title"),
    content: str = typer.Argument(..., help="Note content (markdown)"),
    object_type: str = typer.Option("people", "--type", "-t", help="Object type: people, companies, or deals"),
):
    """Add a note to a person, company, or deal."""
    result = _client().notes.create(object_type, record_id, title, content)
    _out(result)


# --- Tasks ---

@task_app.command("list")
def task_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include completed tasks"),
):
    """List tasks."""
    c = _client()
    data = c.tasks.list(completed=None if all else False)
    tasks = data.get("data", [])
    result = []
    for t in tasks:
        result.append({
            "id": t["id"]["task_id"],
            "content": t.get("content_plaintext", ""),
            "deadline": t.get("deadline_at"),
            "completed": t.get("is_completed", False),
            "assignees": [a.get("referenced_actor_id") for a in t.get("assignees", [])],
        })
    _out({"count": len(result), "tasks": result})


@task_app.command("add")
def task_add(
    content: str = typer.Argument(..., help="Task description"),
    deadline: Optional[str] = typer.Option(None, "--deadline", "-d", help="Deadline (YYYY-MM-DD)"),
    record: Optional[str] = typer.Option(None, "--record", "-r", help="Linked record ID"),
    record_type: Optional[str] = typer.Option("companies", "--type", "-t", help="Linked record type (companies, people)"),
):
    """Create a task."""
    c = _client()
    result = c.tasks.create(
        content=content,
        deadline=deadline,
        linked_object=record_type if record else None,
        linked_record_id=record,
    )
    task = result.get("data", {})
    print(f"Created task: {task.get('id', {}).get('task_id', '')}")
    _out(task)
