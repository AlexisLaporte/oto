# Oto

CLI for business automation — Google Workspace, browser scraping, company data, AI, CRM, and more. Designed for humans and AI agents.

## Installation

```bash
# CLI (standalone)
pipx install git+https://github.com/AlexisLaporte/oto.git

# As a dependency
pip install git+https://github.com/AlexisLaporte/oto.git

# With extras
pip install "oto[browser,ai] @ git+https://github.com/AlexisLaporte/oto.git"
```

### Extras

| Extra | What it adds |
|-------|-------------|
| `browser` | Patchright (undetectable Playwright) |
| `stock` | pyarrow + pandas for SIRENE bulk data |
| `company-fr` | French company API clients |
| `ai` | Anthropic + Mistral SDKs |
| `communication` | Resend email |
| `marketing` | Marketing tools |
| `crm` | CRM clients |
| `search` | Web search APIs |
| `media` | Media APIs |
| `pennylane` | Pennylane accounting |
| `all` | Everything above |

## Configuration

Secrets are loaded from `.otomata/secrets.env` files:

1. **Environment variables** (highest priority)
2. **Project** — `.otomata/secrets.env` in current directory (walks up 4 levels)
3. **User** — `~/.otomata/secrets.env`

```bash
mkdir -p ~/.otomata
cat > ~/.otomata/secrets.env << 'EOF'
SIRENE_API_KEY=xxx
NOTION_API_KEY=secret_xxx
SERPER_API_KEY=xxx
EOF
```

Check status:

```bash
oto config
```

## Quick Reference

```bash
# Google Workspace (OAuth multi-account)
oto google auth myaccount              # Setup OAuth
oto google auth --list                 # List accounts
oto google gmail-search "from:bob" -a myaccount
oto google gmail-send --to bob@x.com --subject "Hi" --body "Hello"
oto google gmail-draft --body "Draft" --reply-to MSG_ID
oto google drive-list --folder-id xxx
oto google docs-headings DOC_ID
oto google calendar-today -a myaccount
oto google calendar-upcoming --days 7

# Browser automation
oto browser linkedin-profile https://linkedin.com/in/someone
oto browser linkedin-company https://linkedin.com/company/example
oto browser crunchbase-company example
oto browser pappers-siren 443061841
oto browser indeed-search "python developer" --location Paris

# French company data (SIRENE)
oto sirene search "otomata"
oto sirene get 443061841
oto company 443061841

# Web search
oto search web "AI agents 2026"
oto search news "Series A"

# Notion
oto notion search "quarterly report"
oto notion page PAGE_ID --blocks

# Enrichment
oto enrichment kaspr-enrich LINKEDIN_ID
oto enrichment hunter-domain example.com

# Accounting
oto pennylane trial-balance --start 2025-01-01 --end 2025-12-31

# Anthropic usage
oto anthropic today
oto anthropic cost --days 30

# WhatsApp
oto whatsapp send "Contact Name" "Hello!"
oto whatsapp chats
```

## Claude Code Skills

Oto ships with 9 skills for Claude Code:

```bash
oto skills list              # See available skills
oto skills enable --all      # Enable all (symlinks to ~/.claude/skills/)
oto skills disable oto-pennylane
```

| Skill | Description |
|-------|-------------|
| `oto-anthropic` | Anthropic API usage and cost tracking |
| `oto-browser` | Browser automation + LinkedIn, Crunchbase, Pappers, Indeed, G2 |
| `oto-enrichment` | Contact enrichment (Kaspr, Hunter, Lemlist) |
| `oto-google` | Gmail, Drive, Docs, Calendar |
| `oto-notion` | Notion workspace |
| `oto-pennylane` | Pennylane accounting |
| `oto-search` | Web and news search (Serper) |
| `oto-sirene` | SIRENE INSEE company data |
| `oto-whatsapp` | WhatsApp messaging |

## Development

```bash
git clone https://github.com/AlexisLaporte/oto.git
cd oto
pip install -e ".[all]"
oto config
```

## License

MIT
