"""Oto CLI - unified entry point for all tools."""

import typer

app = typer.Typer(
    name="oto",
    help="CLI tools for automating tasks with Google, Notion, and more.",
    no_args_is_help=True,
)

from oto.commands import google, notion, browser, sirene, search, enrichment, pennylane, anthropic, company, skills, whatsapp, folk, audio

app.add_typer(audio.app, name="audio")
app.add_typer(google.app, name="google")
app.add_typer(notion.app, name="notion")
app.add_typer(browser.app, name="browser")
app.add_typer(browser.linkedin_app, name="linkedin")
app.add_typer(sirene.app, name="sirene")
app.add_typer(search.app, name="search")
app.add_typer(enrichment.app, name="enrichment")
app.add_typer(pennylane.app, name="pennylane")
app.add_typer(anthropic.app, name="anthropic")
app.add_typer(company.app, name="company")
app.add_typer(skills.app, name="skills")
app.add_typer(whatsapp.app, name="whatsapp")
app.add_typer(folk.app, name="folk")


@app.command("config")
def show_config():
    """Show current configuration and detected secrets."""
    from pathlib import Path
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
            import sys
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
