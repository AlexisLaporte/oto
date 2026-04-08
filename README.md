# oto — CLI toolkit for AI agents

Your LLM already uses `gh` for GitHub, `aws` for AWS, `gcloud` for GCP.
**oto** covers the long tail — the SaaS products that don't have a CLI.

Each connector ships with a **SKILL.md** — an instruction manual that teaches your AI agent how to use it. Run `oto skills enable --all` and your Claude Code / Cursor / Aider gets instant context on 15+ APIs.

## Why CLI over MCP?

| | CLI | MCP |
|---|---|---|
| Token cost | ~80 tokens (prompt + `--help`) | 4-32x more (full schema in context) |
| Reliability | 100% | ~72% ([source](https://scalekit.com)) |
| Setup | `pipx install oto-cli` | Server + transport + config |
| Composability | Pipes: `oto sirene search "fintech" \| jq '.[]'` | None |
| Works with | Every LLM, every framework | MCP-compatible clients only |

## Installation

```bash
# Standalone CLI
pipx install oto-cli

# With specific connectors
pipx install "oto-cli[google,browser]"

# All connectors
pipx install "oto-cli[all]"

# Development
git clone https://github.com/AlexisLaporte/oto.git
cd oto && pip install -e ".[all]"
```

## Connectors

| Command | What it does | Extra |
|---------|-------------|-------|
| `oto google` | Gmail, Drive, Docs, Sheets, Slides, Calendar | `google` |
| `oto browser` | LinkedIn, Crunchbase, Pappers, Indeed, G2, Google | `browser` |
| `oto notion` | Search, pages, databases | — |
| `oto sirene` | French company data (INSEE SIRENE) | — |
| `oto search` | Web & news search (dispatches to Serper or browser) | — |
| `oto serper` | Direct Serper API (web, news, scrape, suggestions) | — |
| `oto enrichment` | Contact enrichment (Kaspr, Hunter, Lemlist) | — |
| `oto pennylane` | Accounting (Pennylane API) | — |
| `oto anthropic` | API usage & cost tracking | `anthropic` |
| `oto whatsapp` | Send & read WhatsApp messages | — |
| `oto attio` | Attio CRM (contacts, companies, deals, tasks) | — |
| `oto folk` | Folk CRM (contacts, companies, deals) | — |
| `oto zoho` | Zoho CRM (records, contacts, deals, notes) | — |
| `oto company` | French company lookup (multi-source) | — |
| `oto audio` | Audio recording, transcription, summaries | — |
| `oto gemini` | Image generation (text-to-image, editing) | — |
| `oto config` | Configuration & secrets management | — |

Connectors without an "Extra" only need `requests` (included in base install).

## Quick start

```bash
# Configure secrets (file-based, default)
mkdir -p ~/.otomata
cat > ~/.otomata/secrets.env << 'EOF'
SERPER_API_KEY=xxx
NOTION_API_KEY=secret_xxx
SIRENE_API_KEY=xxx
EOF

# Or use Scaleway Secret Manager
oto config provider secrets scaleway

# Check config & secrets status
oto config

# Search the web (backend depends on config: serper or browser)
oto search web -q "AI agents 2026"

# Google OAuth setup (per account)
oto google auth myaccount
oto google gmail-search "from:bob" -a myaccount

# Browse LinkedIn
oto browser linkedin profile https://linkedin.com/in/someone

# French company data
oto sirene search "fintech"
```

## Skills for AI agents

The killer feature: each connector comes with a SKILL.md that teaches your LLM how to use it.

```bash
# Enable all skills for Claude Code
oto skills enable --all

# Or pick specific ones
oto skills enable oto-google
oto skills enable oto-search
```

Once enabled, your AI agent sees these instructions in its context and knows exactly which `oto` commands to use, with what arguments, and what output to expect.

## Create your own connector

A connector is 3 files:

```
oto/commands/myservice.py    # CLI commands (Typer app)
oto/tools/myservice/         # API client
skills/oto-myservice/SKILL.md  # LLM instructions
```

See [docs/create-connector.md](docs/create-connector.md) for the full guide.

## How it works

**Auto-discovery** — `cli.py` scans `commands/` at startup. Any Python file exporting a Typer `app` becomes a sub-command. No registry, no config. Drop a file, it appears in `oto --help`.

**Three types of connectors** (same CLI contract: JSON stdout, lazy imports, `get_secret()`):
- **API** — call REST APIs via `requests`. Each client handles auth/pagination/rate-limiting as the API requires. (notion, sirene, search, pennylane, folk...)
- **Browser** — automate a real browser for sites without an API. Async, require `oto-cli[browser]`. (linkedin, crunchbase, pappers, indeed, g2)
- **SDK** — use an official client library. Currently Google Workspace via `google-api-python-client` + OAuth2. Require `oto-cli[google]`.

**Secrets** — provider-based resolution, configured via `oto config provider secrets <file|scaleway>`:
1. Environment variables (always, highest priority)
2. Configured provider: **file** (`.otomata/secrets.env` project → user) or **Scaleway** Secret Manager
3. Default value

**Output contract** — every command prints JSON to stdout, errors to stderr. Composable with `jq`, pipes, scripts.

**Lazy imports** — tool clients are imported inside functions, so the CLI starts fast regardless of how many connectors are installed.

See [docs/concepts.md](docs/concepts.md) for the full architecture guide.

## License

MIT
