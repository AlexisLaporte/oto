# Oto

CLI toolkit for AI agents — covers the long tail of SaaS APIs that don't have a CLI.

Repo: `AlexisLaporte/oto`. Package: `oto-cli` on PyPI (v1.1.0). Command: `oto`.

## Philosophy

- **CLI-first**: everything goes through `oto <command>`, no MCP, no server
- **For AI agents**: JSON on stdout, errors on stderr, composable with pipes
- **Modular**: each connector is a separate file, auto-discovered at startup
- **No over-engineering**: no plugin registry, no ABC, no MCP

## Stack

- Python 3.10+, Typer (CLI), Hatchling (build)
- Google APIs (auth, drive, docs, sheets, slides, gmail, keep)
- o-browser (browser automation, Patchright) — optional
- Requests (HTTP), python-dotenv (secrets)

## Architecture

```
oto/
├── oto/
│   ├── cli.py                  # Dynamic command discovery + main()
│   ├── config.py               # Secrets 3-tier (.otomata/secrets.env)
│   ├── commands/               # 1 file = 1 sub-command (auto-discovered)
│   │   ├── google.py           # drive, docs, sheets, slides, gmail, calendar, auth
│   │   ├── notion.py           # search, page, database
│   │   ├── browser.py          # linkedin, crunchbase, pappers, indeed, g2, google
│   │   ├── sirene.py           # SIRENE API (search, get, stock)
│   │   ├── search.py           # facade: dispatches to serper or browser via config
│   │   ├── serper.py           # direct Serper API (web, news, scrape, suggestions)
│   │   ├── enrichment.py       # kaspr, hunter, lemlist
│   │   ├── pennylane.py        # accounting
│   │   ├── anthropic.py        # usage, cost, summary
│   │   ├── attio.py            # Attio CRM (contacts, companies, deals, tasks)
│   │   ├── folk.py             # Folk CRM
│   │   ├── zoho.py             # Zoho CRM
│   │   ├── company.py          # SIREN lookup multi-source
│   │   ├── whatsapp.py         # WhatsApp messaging
│   │   ├── audio.py            # audio recording, transcription
│   │   ├── gemini.py           # Gemini image generation
│   │   ├── config.py           # config & secrets management
│   │   └── skills.py           # Claude Code skills (enable/disable)
│   └── tools/                  # API clients
│       ├── google/             # gmail, drive, docs, sheets, slides, calendar, keep
│       ├── notion/             # pages, databases, search
│       ├── browser/            # linkedin, crunchbase, pappers, indeed, g2, google
│       ├── whatsapp/           # Node.js bridge (whatsapp-web.js)
│       ├── sirene/             # INSEE SIRENE API
│       ├── serper/             # Google search (web, news)
│       ├── anthropic/          # Admin API (usage, costs)
│       ├── pennylane/          # Accounting
│       ├── attio/              # Attio CRM
│       ├── kaspr/, hunter/, lemlist/  # Enrichment & outreach
│       └── folk/, zoho/, slack/, resend/  # CRM & messaging
├── skills/                     # Claude Code skills
│   └── oto-*/SKILL.md          # LLM instruction manuals
└── pyproject.toml              # entry point: oto = "oto.cli:main"
```

## Adding a new connector

A connector = 3 files:

1. **`commands/myservice.py`** — Typer app, exports `app`
2. **`tools/myservice/`** — API client(s)
3. **`skills/oto-myservice/SKILL.md`** — LLM instructions

See `docs/create-connector.md` for details.

## Command pattern

Each `commands/*.py` file:
```python
import typer
import json
from typing import Optional

app = typer.Typer(help="My service description")

@app.command("do-thing")
def do_thing(
    query: str = typer.Argument(..., help="What to do"),
    max_results: int = typer.Option(20, "--max-results", "-n"),
):
    """Do a thing."""
    from oto.tools.myservice.client import MyServiceClient
    client = MyServiceClient()
    results = client.do_thing(query=query, max_results=max_results)
    print(json.dumps(results, indent=2))
```

Key rules:
- `app = typer.Typer()` exported, auto-discovered by `cli.py`
- Tool imports **inside functions** (lazy) so the CLI stays fast
- Always `print(json.dumps(..., indent=2))` for output
- Missing secrets raise `ValueError`, caught by `main()` → clean stderr message

## Secrets & Config

Provider-based resolution, configured via `oto config provider secrets <file|scaleway>`:
1. Environment variables (always, highest priority)
2. Configured provider: **file** (`.otomata/secrets.env` project → user) or **Scaleway** Secret Manager
3. Default value

```bash
oto config                        # show providers + secrets status
oto config provider secrets file  # switch to file-based secrets
oto config provider search serper # switch search to serper (default) or browser
oto config secrets-push           # upload local secrets.env → Scaleway
oto config secrets-pull           # download Scaleway → local secrets.env
```

## Search

Facade `oto search` dispatches to backend based on `search_provider` config:

| Command | Backend | Notes |
|---------|---------|-------|
| `oto search web -q "..."` | config-based | serper (default) or browser |
| `oto search news -q "..."` | serper only | no browser equivalent |
| `oto serper web/news/scrape/suggestions` | Serper API | direct access |
| `oto browser google -q "..."` | Chrome | needs `--profile` to avoid bot detection |

## Google OAuth

Tokens stored in `~/.otomata/google-oauth-token-{name}.json`.

Add an account: `oto google auth <name>` — opens browser for OAuth flow.
List accounts: `oto google auth --list`.

## Skills (Claude Code)

Skills = SKILL.md files in `skills/oto-*/`, symlinked to `~/.claude/skills/`.

```bash
oto skills list                    # see status
oto skills enable --all            # enable all
oto skills enable oto-google       # enable one
oto skills disable oto-pennylane   # disable one
```

## Release

Package: `oto-cli` on PyPI. PyPI token in `pass otomata/PYPI_TOKEN`.

```bash
# Bump version in oto/__init__.py, then:
hatch build && hatch publish -u __token__ -a "$(pass otomata/PYPI_TOKEN)"
gh release create vX.Y.Z --generate-notes dist/*
```

## Docs

Detailed docs in `docs/`:
- `concepts.md` — architecture, connector types (API/browser/SDK), secrets, output contract, skills
- `create-connector.md` — step-by-step guide to add a connector (command + client + skill)
- `installation.md` — setup and dependencies
- `gmail-oauth-setup.md` — OAuth multi-account setup for Gmail
- `google-service-account-setup.md` — Google service account setup
