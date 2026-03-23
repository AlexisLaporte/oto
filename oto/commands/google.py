"""Google Workspace commands (Drive, Docs, Sheets, Slides, Gmail, Calendar, Auth)."""

import typer
from typing import Optional

app = typer.Typer(help="Google Workspace tools (Drive, Docs, Sheets, Slides, Gmail, Calendar)")


def _apply_signature(client, body: str, html: Optional[str]) -> Optional[str]:
    """Convert plain text body to HTML with Gmail signature appended."""
    import html as html_mod
    signature = client.get_signature()
    if not signature:
        return html
    body_html = html or '<div dir="ltr">' + html_mod.escape(body).replace('\n', '<br>') + '</div>'
    return body_html + '<br>--<br>' + signature


@app.command("drive-list")
def drive_list(
    folder_id: Optional[str] = typer.Option(None, help="Filter by parent folder ID"),
    query: Optional[str] = typer.Option(None, help="Custom query filter"),
    limit: int = typer.Option(100, help="Max results"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List files in Google Drive."""
    from oto.tools.google.drive.lib.drive_client import DriveClient
    import json

    client = DriveClient(account=account)
    files = client.list_files(folder_id=folder_id, query=query, page_size=limit)
    print(json.dumps({"count": len(files), "files": files}, indent=2))


@app.command("drive-download")
def drive_download(
    file_id: str = typer.Argument(..., help="Google Drive file ID"),
    output: str = typer.Argument(..., help="Output path"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Download a file from Google Drive."""
    from oto.tools.google.drive.lib.drive_client import DriveClient

    client = DriveClient(account=account)
    result = client.download_file(file_id, output)
    print(f"Downloaded: {result['filename']} -> {result['output_path']}")


@app.command("drive-upload")
def drive_upload(
    file_path: str = typer.Argument(..., help="Local file path to upload"),
    folder_id: Optional[str] = typer.Option(None, help="Target folder ID in Drive"),
    name: Optional[str] = typer.Option(None, help="Custom filename (defaults to local name)"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Upload a file to Google Drive."""
    from oto.tools.google.drive.lib.drive_client import DriveClient
    import json

    client = DriveClient(account=account)
    result = client.upload_file(local_path=file_path, folder_id=folder_id, file_name=name)
    print(json.dumps(result, indent=2))


@app.command("drive-move")
def drive_move(
    file_id: str = typer.Argument(..., help="Google Drive file ID to move"),
    folder_id: str = typer.Argument(..., help="Destination folder ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Move a file to a different folder in Google Drive."""
    from oto.tools.google.drive.lib.drive_client import DriveClient
    import json

    client = DriveClient(account=account)
    result = client.move_file(file_id, folder_id)
    print(json.dumps(result, indent=2))


@app.command("docs-create")
def docs_create(
    title: str = typer.Argument(..., help="Document title"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Text/markdown file to import as content"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Parse markdown formatting (headings, bold, lists, quotes)"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Create a new Google Doc, optionally importing content from a file."""
    from oto.tools.google.docs.lib.docs_client import DocsClient
    import json

    content = ''
    if file:
        with open(file, 'r', encoding='utf-8') as fh:
            content = fh.read()
        if not markdown and file.endswith('.md'):
            markdown = True

    client = DocsClient(account=account)
    result = client.create(title, content, markdown=markdown)
    if file:
        result['imported'] = file
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("docs-write")
def docs_write(
    doc_id: str = typer.Argument(..., help="Google Docs document ID"),
    file: str = typer.Argument(..., help="Text/markdown file to write"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Parse markdown formatting"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Replace entire content of a Google Doc with a file's content."""
    from oto.tools.google.docs.lib.docs_client import DocsClient
    import json

    with open(file, 'r', encoding='utf-8') as fh:
        content = fh.read()

    if not markdown and file.endswith('.md'):
        markdown = True

    client = DocsClient(account=account)
    result = client.replace_content(doc_id, content, markdown=markdown)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("docs-headings")
def docs_headings(
    doc_id: str = typer.Argument(..., help="Google Docs document ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List headings in a Google Doc."""
    from oto.tools.google.docs.lib.docs_client import DocsClient
    import json

    client = DocsClient(account=account)
    headings = client.list_headings(doc_id)
    print(json.dumps(headings, indent=2))


@app.command("docs-section")
def docs_section(
    doc_id: str = typer.Argument(..., help="Google Docs document ID"),
    heading: str = typer.Argument(..., help="Heading text to find"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Get content of a section in a Google Doc."""
    from oto.tools.google.docs.lib.docs_client import DocsClient

    client = DocsClient(account=account)
    section = client.get_section_content(doc_id, heading)
    if section:
        print(f"# {section.title}\n")
        print(section.content)
    else:
        print(f"Section not found: {heading}")
        raise typer.Exit(1)


@app.command("auth")
def auth(
    name: str = typer.Argument("default", help="Account name (e.g. 'gmail', 'work')"),
    list_accounts: bool = typer.Option(False, "--list", "-l", help="List configured accounts"),
):
    """Set up or list Google OAuth accounts."""
    from oto.tools.google.credentials import list_accounts as _list_accounts, setup_account, DEFAULT_SCOPES as DRIVE_SCOPES
    from oto.tools.google.gmail.lib.gmail_client import SCOPES as GMAIL_SCOPES
    from oto.tools.google.calendar.lib.calendar_client import SCOPES as CALENDAR_SCOPES

    ALL_SCOPES = list(set(GMAIL_SCOPES + CALENDAR_SCOPES + DRIVE_SCOPES))

    if list_accounts:
        accounts = _list_accounts()
        if not accounts:
            print("No accounts configured. Run: oto google auth <name>")
        else:
            for a in accounts:
                print(f"  {a}")
        return

    print(f"Setting up account '{name}'... Opening browser for Google consent.")
    setup_account(name, ALL_SCOPES)
    print(f"Account '{name}' configured.")


@app.command("calendar-list")
def calendar_list(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List available calendars."""
    from oto.tools.google.calendar.lib.calendar_client import CalendarClient
    import json

    client = CalendarClient(account=account)
    calendars = client.list_calendars()
    print(json.dumps({"count": len(calendars), "calendars": calendars}, indent=2, ensure_ascii=False))


@app.command("calendar-today")
def calendar_today(
    calendar_id: str = typer.Option("primary", "--calendar", "-c", help="Calendar ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List today's events."""
    from oto.tools.google.calendar.lib.calendar_client import CalendarClient
    import json

    client = CalendarClient(account=account)
    events = client.today(calendar_id=calendar_id)
    print(json.dumps({"count": len(events), "events": events}, indent=2, ensure_ascii=False))


@app.command("calendar-upcoming")
def calendar_upcoming(
    days: int = typer.Option(7, "--days", "-d", help="Number of days ahead"),
    calendar_id: str = typer.Option("primary", "--calendar", "-c", help="Calendar ID"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max events"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List upcoming events (default: next 7 days)."""
    from oto.tools.google.calendar.lib.calendar_client import CalendarClient
    import json

    client = CalendarClient(account=account)
    events = client.upcoming(days=days, calendar_id=calendar_id, max_results=limit)
    print(json.dumps({"count": len(events), "events": events}, indent=2, ensure_ascii=False))


@app.command("calendar-search")
def calendar_search(
    query: str = typer.Argument(..., help="Search query"),
    days: int = typer.Option(30, "--days", "-d", help="Search window in days"),
    calendar_id: str = typer.Option("primary", "--calendar", "-c", help="Calendar ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max events"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Search calendar events."""
    from oto.tools.google.calendar.lib.calendar_client import CalendarClient
    from datetime import datetime, timedelta, timezone
    import json

    client = CalendarClient(account=account)
    now = datetime.now(timezone.utc)
    events = client.list_events(
        calendar_id=calendar_id,
        time_min=now.isoformat(),
        time_max=(now + timedelta(days=days)).isoformat(),
        max_results=limit,
        query=query,
    )
    print(json.dumps({"count": len(events), "events": events}, indent=2, ensure_ascii=False))


@app.command("calendar-get")
def calendar_get(
    event_id: str = typer.Argument(..., help="Event ID"),
    calendar_id: str = typer.Option("primary", "--calendar", "-c", help="Calendar ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Get details of a calendar event."""
    from oto.tools.google.calendar.lib.calendar_client import CalendarClient
    import json

    client = CalendarClient(account=account)
    event = client.get_event(event_id, calendar_id=calendar_id)
    print(json.dumps(event, indent=2, ensure_ascii=False))


@app.command("gmail-list")
def gmail_list(
    query: Optional[str] = typer.Option(None, help="Gmail search query"),
    label: Optional[str] = typer.Option(None, help="Filter by label ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max messages"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """List recent Gmail messages."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    label_ids = [label] if label else None
    messages = client.list_messages(query=query, label_ids=label_ids, max_results=limit)
    print(json.dumps({"count": len(messages), "messages": messages}, indent=2, ensure_ascii=False))


@app.command("gmail-search")
def gmail_search(
    query: str = typer.Argument(..., help="Gmail search query (e.g. 'is:unread', 'from:user@example.com')"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max messages"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Search Gmail messages."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    messages = client.search(query=query, max_results=limit)
    print(json.dumps({"count": len(messages), "messages": messages}, indent=2, ensure_ascii=False))


@app.command("gmail-get")
def gmail_get(
    message_id: str = typer.Argument(..., help="Gmail message ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Read a Gmail message."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    message = client.get_message(message_id)
    print(json.dumps(message, indent=2, ensure_ascii=False))


@app.command("gmail-attachments")
def gmail_attachments(
    message_id: str = typer.Argument(..., help="Gmail message ID"),
    output: str = typer.Option(".", "--output", "-o", help="Output directory"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Download attachments from a Gmail message."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    files = client.download_attachments(message_id, output)
    print(json.dumps({"count": len(files), "files": files}, indent=2, ensure_ascii=False))


@app.command("gmail-draft")
def gmail_draft(
    to: Optional[str] = typer.Option(None, help="Recipient email (auto-detected with --reply-to)"),
    subject: Optional[str] = typer.Option(None, help="Email subject (auto-detected with --reply-to)"),
    body: str = typer.Option(..., help="Email body (plain text)"),
    html: Optional[str] = typer.Option(None, help="Email body (HTML). If provided, sent as multipart alternative with plain text."),
    cc: Optional[str] = typer.Option(None, help="CC recipients"),
    bcc: Optional[str] = typer.Option(None, help="BCC recipients"),
    reply_to: Optional[str] = typer.Option(None, "--reply-to", "-r", help="Message ID to reply to (threads the draft)"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-f", help="File paths to attach"),
    sign: bool = typer.Option(True, "--sign/--no-sign", help="Append Gmail signature"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Create a draft email in Gmail. Use --reply-to for threaded replies."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    final_html = _apply_signature(client, body, html) if sign else html
    if reply_to:
        result = client.create_draft_reply(message_id=reply_to, body=body, html=final_html, cc=cc, attachments=attach)
    else:
        if not to or not subject:
            raise typer.BadParameter("--to and --subject are required (unless using --reply-to)")
        result = client.create_draft(to=to, subject=subject, body=body, html=final_html, cc=cc, bcc=bcc, attachments=attach)
    print(json.dumps(result, indent=2))


@app.command("gmail-reply")
def gmail_reply(
    message_id: str = typer.Argument(..., help="Gmail message ID to reply to"),
    body: str = typer.Option(..., help="Reply body (plain text)"),
    html: Optional[str] = typer.Option(None, help="Reply body (HTML)"),
    cc: Optional[str] = typer.Option(None, help="CC recipients"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-f", help="File paths to attach"),
    sign: bool = typer.Option(True, "--sign/--no-sign", help="Append Gmail signature"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Reply to a Gmail message (preserves thread)."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    final_html = _apply_signature(client, body, html) if sign else html
    result = client.reply(message_id=message_id, body=body, html=final_html, cc=cc, attachments=attach)
    print(json.dumps(result, indent=2))


@app.command("gmail-send")
def gmail_send(
    to: str = typer.Option(..., help="Recipient email"),
    subject: str = typer.Option(..., help="Email subject"),
    body: str = typer.Option(..., help="Email body (plain text)"),
    html: Optional[str] = typer.Option(None, help="Email body (HTML)"),
    cc: Optional[str] = typer.Option(None, help="CC recipients"),
    bcc: Optional[str] = typer.Option(None, help="BCC recipients"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-f", help="File paths to attach"),
    sign: bool = typer.Option(True, "--sign/--no-sign", help="Append Gmail signature"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Send an email via Gmail."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    final_html = _apply_signature(client, body, html) if sign else html
    result = client.send(to=to, subject=subject, body=body, html=final_html, cc=cc, bcc=bcc, attachments=attach)
    print(json.dumps(result, indent=2))


@app.command("gmail-archive")
def gmail_archive(
    message_ids: Optional[list[str]] = typer.Argument(None, help="Gmail message IDs to archive"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Archive all messages matching this Gmail query"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Archive Gmail messages (remove from inbox)."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    import json

    client = GmailClient(account=account)
    ids = list(message_ids or [])
    if query:
        msgs = client.search(query=query, max_results=100)
        ids.extend(m['id'] for m in msgs if 'INBOX' in m.get('labelIds', []))
    if not ids:
        print(json.dumps({"archived": 0, "message": "No messages to archive"}))
        return
    results = client.archive_messages(ids)
    print(json.dumps({"archived": len(results), "results": results}, indent=2))


@app.command("sheets-create")
def sheets_create(
    title: str = typer.Argument(..., help="Spreadsheet title"),
    csv_path: Optional[str] = typer.Option(None, "--csv", "-c", help="CSV file to import"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Create a new Google Sheets spreadsheet, optionally importing a CSV."""
    from oto.tools.google.sheets.lib.sheets_client import SheetsClient
    import json

    client = SheetsClient(account=account)
    result = client.create(title)
    if csv_path:
        client.write_csv(result['id'], csv_path)
        result['imported'] = csv_path
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("sheets-info")
def sheets_info(
    spreadsheet_id: str = typer.Argument(..., help="Google Sheets spreadsheet ID"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Get spreadsheet metadata (title, sheet names, dimensions)."""
    from oto.tools.google.sheets.lib.sheets_client import SheetsClient
    import json

    client = SheetsClient(account=account)
    meta = client.get_metadata(spreadsheet_id)
    print(json.dumps(meta, indent=2, ensure_ascii=False))


@app.command("sheets-read")
def sheets_read(
    spreadsheet_id: str = typer.Argument(..., help="Google Sheets spreadsheet ID"),
    range: str = typer.Argument("A:ZZ", help="Cell range (e.g. 'Sheet1!A1:D10', 'A:ZZ')"),
    format: str = typer.Option("csv", "--format", "-f", help="Output format: csv or json"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Read data from a Google Sheets spreadsheet."""
    from oto.tools.google.sheets.lib.sheets_client import SheetsClient
    import json

    client = SheetsClient(account=account)

    if format == "csv":
        print(client.read_csv(spreadsheet_id, range), end="")
    else:
        rows = client.read(spreadsheet_id, range)
        print(json.dumps({"rows": len(rows), "data": rows}, indent=2, ensure_ascii=False))


@app.command("sheets-write")
def sheets_write(
    spreadsheet_id: str = typer.Argument(..., help="Google Sheets spreadsheet ID"),
    csv_path: str = typer.Argument(..., help="Path to CSV file to write"),
    sheet: Optional[str] = typer.Option(None, "--sheet", "-s", help="Target sheet name"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Write a CSV file to a Google Sheets spreadsheet (overwrites sheet)."""
    from oto.tools.google.sheets.lib.sheets_client import SheetsClient
    import json

    client = SheetsClient(account=account)
    result = client.write_csv(spreadsheet_id, csv_path, sheet_name=sheet)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("sheets-append")
def sheets_append(
    spreadsheet_id: str = typer.Argument(..., help="Google Sheets spreadsheet ID"),
    csv_path: str = typer.Argument(..., help="Path to CSV file with rows to append"),
    range: str = typer.Option("A:ZZ", "--range", "-r", help="Range to append to"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Google account name"),
):
    """Append rows from a CSV file to a Google Sheets spreadsheet."""
    from oto.tools.google.sheets.lib.sheets_client import SheetsClient
    import csv as csv_mod
    import json

    client = SheetsClient(account=account)
    with open(csv_path, 'r', encoding='utf-8') as f:
        values = list(csv_mod.reader(f))
    result = client.append(spreadsheet_id, range, values)
    print(json.dumps(result, indent=2, ensure_ascii=False))
