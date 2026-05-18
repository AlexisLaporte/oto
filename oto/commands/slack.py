"""Slack commands (send, read, list-channels, find-user)."""

import json
import sys
from typing import Optional

import typer

app = typer.Typer(help="Slack messaging — channels, DMs, history")


def _client(default_as_user: bool = True):
    """Default `as_user=True` for the CLI: outbound human-style com (Oto pour Alexis).

    Pass `default_as_user=False` for automation that should look like the bot app.
    """
    from oto.tools.slack import SlackClient
    return SlackClient(default_as_user=default_as_user)


@app.command("send")
def send(
    channel: str = typer.Argument(..., help="Channel ID, channel name, user ID, or @email for a DM"),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Message text (or read from stdin)"),
    thread_ts: Optional[str] = typer.Option(None, "--thread", help="Thread parent ts to reply into"),
    as_bot: bool = typer.Option(False, "--as-bot", help="Post as the bot app (default: as the user)"),
):
    """Send a Slack message. Text from --text or stdin.

    Default posts as the human user (Oto pour Alexis). Use --as-bot to post as
    the bot app (useful for automated notifications).

    If `channel` starts with `@` and contains `.`, it's treated as an email and
    resolved to a DM channel via users.lookupByEmail + conversations.open.
    """
    client = _client(default_as_user=not as_bot)

    if text is None:
        if sys.stdin.isatty():
            raise typer.BadParameter("Provide --text or pipe text to stdin")
        text = sys.stdin.read().rstrip()
    if not text:
        raise typer.BadParameter("Empty message")

    target = channel
    if channel.startswith("@") and "." in channel:
        email = channel.lstrip("@")
        user = client.find_user_by_email(email)["user"]
        target = client.open_dm(user["id"])["channel"]["id"]

    result = client.post_message(target, text=text, thread_ts=thread_ts)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("delete")
def delete(
    channel: str = typer.Argument(..., help="Channel ID"),
    ts: str = typer.Argument(..., help="Message timestamp"),
    as_bot: bool = typer.Option(False, "--as-bot", help="Delete a bot-posted message"),
):
    """Delete a message. Must use the same token that posted it."""
    client = _client(default_as_user=not as_bot)
    result = client.delete_message(channel, ts)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("list-channels")
def list_channels(
    types: str = typer.Option("public_channel", help="Types: public_channel,private_channel,mpim,im"),
):
    """List Slack channels visible to the bot."""
    channels = _client().list_channels(types=types)
    print(json.dumps(channels, indent=2, ensure_ascii=False))


@app.command("read")
def read(
    channel: str = typer.Argument(..., help="Channel ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max messages"),
):
    """Read recent messages from a channel."""
    result = _client().history(channel, limit=limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("find-user")
def find_user(
    email: str = typer.Argument(..., help="Email address"),
):
    """Look up a Slack user by email."""
    result = _client().find_user_by_email(email)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("dm")
def open_dm(
    user: str = typer.Argument(..., help="User ID (or email — auto-resolved)"),
):
    """Open a DM channel with a user and print the channel ID."""
    client = _client()
    user_id = user
    if "@" in user and "." in user:
        user_id = client.find_user_by_email(user.lstrip("@"))["user"]["id"]
    result = client.open_dm(user_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
