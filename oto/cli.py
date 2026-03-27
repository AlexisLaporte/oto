"""Oto CLI - composable toolkit for AI agents."""

import importlib
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="oto",
    help="CLI toolkit for AI agents. JSON on stdout, composable with pipes.",
    no_args_is_help=True,
)

# Auto-discover commands from oto/commands/*.py
_commands_dir = Path(__file__).parent / "commands"
for _cmd_file in sorted(_commands_dir.glob("*.py")):
    if _cmd_file.name.startswith("_"):
        continue
    _module_name = _cmd_file.stem
    try:
        _module = importlib.import_module(f"oto.commands.{_module_name}")
    except ImportError:
        continue
    if hasattr(_module, "app"):
        app.add_typer(_module.app, name=_module_name)


@app.command("config")
def show_config():
    """Show current configuration and detected secrets."""
    from oto.config import _find_project_secrets, _get_user_secrets, get_secret

    project_secrets = _find_project_secrets()
    user_secrets = _get_user_secrets()

    print("Secrets files:")
    print(f"  Project: {project_secrets or '.otomata/secrets.env (not found)'}")
    print(f"  User:    {user_secrets}{' (exists)' if user_secrets.exists() else ' (not found)'}")
    print()
    print("Secrets status:")
    secrets = [
        "GOOGLE_SERVICE_ACCOUNT",
        "GOOGLE_OAUTH_CLIENT",
        "NOTION_API_KEY",
        "LINKEDIN_COOKIE",
        "SIRENE_API_KEY",
        "SERPER_API_KEY",
        "KASPR_API_KEY",
        "HUNTER_API_KEY",
        "LEMLIST_API_KEY",
        "PENNYLANE_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_ADMIN_API_KEY",
        "FOLK_API_KEY",
        "ATTIO_API_KEY",
        "TULS_API_TOKEN",
    ]
    for name in secrets:
        status = "+" if get_secret(name) else "-"
        print(f"  {status} {name}")


def main():
    try:
        app()
    except ValueError as e:
        if "not found. Set it via:" in str(e):
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
