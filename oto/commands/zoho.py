"""Zoho CRM commands."""

import json
import typer
from typing import Optional

app = typer.Typer(help="Zoho CRM — records, contacts, deals, notes")


def _out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _client():
    from oto.tools.zoho import ZohoClient
    return ZohoClient()


def _parse_fields(fields: list[str]) -> dict:
    """Parse --field key=value pairs into a dict."""
    result = {}
    for f in fields:
        if "=" not in f:
            raise typer.BadParameter(f"Invalid field format: {f!r} (expected key=value)")
        key, value = f.split("=", 1)
        result[key] = value
    return result


@app.command("modules")
def modules():
    """List available CRM modules."""
    mods = _client().list_modules()
    result = [{"api_name": m["api_name"], "label": m.get("plural_label", m.get("singular_label", ""))} for m in mods]
    _out({"count": len(result), "modules": result})


@app.command("records")
def records(
    module: str = typer.Argument(..., help="Module API name (Contacts, Leads, Deals, Accounts...)"),
    max_results: int = typer.Option(20, "--max-results", "-n"),
    fields: Optional[str] = typer.Option(None, "--fields", help="Comma-separated field names"),
    page: int = typer.Option(1, "--page", "-p"),
):
    """List records from a module."""
    data = _client().list_records(module, page=page, per_page=max_results, fields=fields)
    records_list = data.get("data", [])
    _out({"count": len(records_list), "records": records_list})


@app.command("record")
def record(
    module: str = typer.Argument(..., help="Module API name"),
    record_id: str = typer.Argument(..., help="Record ID"),
):
    """Get a single record."""
    _out(_client().get_record(module, record_id))


@app.command("search")
def search(
    module: str = typer.Argument(..., help="Module API name"),
    criteria: str = typer.Argument(..., help="Search criteria, e.g. '(Email:equals:john@doe.com)'"),
    max_results: int = typer.Option(20, "--max-results", "-n"),
    page: int = typer.Option(1, "--page", "-p"),
):
    """Search records in a module."""
    data = _client().search_records(module, criteria=criteria, page=page, per_page=max_results)
    records_list = data.get("data", [])
    _out({"count": len(records_list), "records": records_list})


@app.command("add-record")
def add_record(
    module: str = typer.Argument(..., help="Module API name"),
    fields: list[str] = typer.Option(..., "--field", "-f", help="Field key=value"),
):
    """Create a record."""
    data = _parse_fields(fields)
    _out(_client().create_record(module, data))


@app.command("update-record")
def update_record(
    module: str = typer.Argument(..., help="Module API name"),
    record_id: str = typer.Argument(..., help="Record ID"),
    fields: list[str] = typer.Option(..., "--field", "-f", help="Field key=value"),
):
    """Update a record."""
    data = _parse_fields(fields)
    _out(_client().update_record(module, record_id, data))


@app.command("delete-record")
def delete_record(
    module: str = typer.Argument(..., help="Module API name"),
    record_id: str = typer.Argument(..., help="Record ID"),
):
    """Delete a record."""
    _out(_client().delete_record(module, record_id))


@app.command("notes")
def notes(
    module: str = typer.Argument(..., help="Module API name"),
    record_id: str = typer.Argument(..., help="Record ID"),
):
    """List notes for a record."""
    items = _client().list_notes(module, record_id)
    _out({"count": len(items), "notes": items})


@app.command("add-note")
def add_note(
    module: str = typer.Argument(..., help="Module API name"),
    record_id: str = typer.Argument(..., help="Record ID"),
    title: str = typer.Argument(..., help="Note title"),
    content: str = typer.Argument(..., help="Note content"),
):
    """Add a note to a record."""
    _out(_client().create_note(module, record_id, title, content))
