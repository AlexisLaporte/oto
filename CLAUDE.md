# Oto

CLI unifié pour automatiser des tâches, utilisé par des humains et des agents AI via Bash.

Repo : `AlexisLaporte/oto` (historique conservé depuis otomata-tools).

## Philosophie

- **CLI-first** : tout passe par `oto <commande>`, pas de MCP, pas de serveur
- **Pour les agents AI** : output JSON sur stdout, erreurs sur stderr, composable avec pipes
- **Pas de sur-ingénierie** : pas de plugin registry, pas d'ABC, pas de MCP

## Stack

- Python 3.10+, Typer (CLI), Hatchling (build)
- Google APIs (auth, drive, docs, sheets, slides, gmail, keep)
- o-browser `/data/projects/o-browser` (browser automation, Patchright)
- Requests (HTTP), python-dotenv (secrets)

## Architecture

```
/data/oto/
├── oto/                        # Package Python
│   ├── __init__.py             # v0.1.0
│   ├── cli.py                  # Assembleur Typer + main() error handler
│   ├── config.py               # Secrets 3-tier
│   ├── commands/               # 1 fichier par domaine
│   │   ├── google.py           # drive, docs, sheets, slides, gmail, auth
│   │   ├── notion.py           # search, page, database
│   │   ├── browser.py          # linkedin, crunchbase, pappers, indeed, g2
│   │   ├── sirene.py           # SIRENE API (search, get, stock)
│   │   ├── search.py           # web, news (serper)
│   │   ├── enrichment.py       # kaspr, hunter, lemlist
│   │   ├── pennylane.py        # comptabilité
│   │   ├── anthropic.py        # usage, cost, summary
│   │   ├── company.py          # SIREN lookup multi-source
│   │   ├── whatsapp.py         # WhatsApp messaging
│   │   └── skills.py           # Claude Code skills management (enable/disable)
│   └── tools/                  # 30+ modules clients API
│       ├── google/             # gmail/, drive/, docs/, sheets/, slides/, keep/, credentials.py
│       ├── sirene/
│       ├── browser/            # linkedin, crunchbase, pappers, indeed, g2
│       ├── whatsapp/
│       ├── common/
│       ├── anthropic/
│       ├── kaspr/, hunter/, lemlist/
│       ├── pennylane/
│       └── ... (apollo, attio, folk, figma, groq, etc.)
├── skills/                     # Claude Code skills (source de vérité)
│   └── oto-*/SKILL.md          # 9 skills, symlinked vers ~/.claude/skills/
└── pyproject.toml              # entry point: oto = "oto.cli:main"
```

## Commandes

```bash
# Installation
pip install -e .                              # deps de base
pip install -e ".[all]"                       # toutes les deps optionnelles

# Exemples
oto --help
oto google gmail-search "from:nicolas" -a otomata -n 5
oto google gmail-send "dest@email.com" "Sujet" "Corps" -a otomata
oto google gmail-archive -q "subject:newsletter" -a perso
oto google auth --list
oto google auth moncompte                     # lance OAuth flow dans le browser
oto sirene search "otomata"
oto browser linkedin-profile "https://linkedin.com/in/someone"
oto search web "AI agents 2026"
oto config                                    # affiche secrets détectés

# Skills Claude Code
oto skills list                              # skills disponibles + statut
oto skills enable --all                      # active tous les skills (symlinks)
oto skills disable oto-pennylane             # désactive un skill
```

## Comptes Google OAuth

Les tokens sont dans `~/.otomata/google-oauth-token-{name}.json`.

| Compte | Email | Usage |
|--------|-------|-------|
| `otomata` | alexis@otomata.tech | Compte pro |
| `perso` | alexis.laporte@gmail.com | Compte perso |
| `sarahetalexis` | sarah.et.alexis.sl@gmail.com | Compte famille |

**ATTENTION** : il n'existe PAS de compte `default` ni `gmail`. Ces anciens noms ont été supprimés/renommés. Utiliser `-a otomata` ou `-a perso`.

Pour ajouter un compte : `oto google auth <nom>` → ouvre le browser pour le flow OAuth.

## Secrets

Résolution 3-tier (premier trouvé gagne) :
1. Variables d'environnement
2. `.otomata/secrets.env` dans le projet (remonte 4 niveaux)
3. `~/.otomata/secrets.env` (user-level)

Secrets utilisés : `GOOGLE_SERVICE_ACCOUNT`, `GOOGLE_OAUTH_CLIENT`, `NOTION_API_KEY`, `LINKEDIN_COOKIE`, `SIRENE_API_KEY`, `SERPER_API_KEY`, `KASPR_API_KEY`, `HUNTER_API_KEY`, `LEMLIST_API_KEY`, `PENNYLANE_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_ADMIN_API_KEY`.

Le fichier OAuth client Google est dans `~/.otomata/google-oauth-client.json`.

## Pattern pour les commandes

Chaque fichier `commands/*.py` :
```python
import typer
import json
from typing import Optional

app = typer.Typer()

@app.command("gmail-search")
def gmail_search(
    query: str = typer.Argument(..., help="Gmail search query"),
    account: Optional[str] = typer.Option(None, "--account", "-a"),
    max_results: int = typer.Option(20, "--max-results", "-n"),
):
    """Search Gmail messages."""
    from oto.tools.google.gmail.lib.gmail_client import GmailClient
    client = GmailClient(account=account)
    results = client.search(query=query, max_results=max_results)
    print(json.dumps(results, indent=2))
```

Points clés :
- `app = typer.Typer()` exporté, assemblé dans `cli.py` via `app.add_typer()`
- Imports des clients **locaux** (dans la fonction, pas en haut du fichier) pour que le CLI reste rapide
- Toujours `print(json.dumps(..., indent=2))` pour l'output
- Erreurs de secrets manquants catchées dans `main()` → message propre sur stderr (pas de traceback)

## Prod

- `otomata.tech` → tuls.me:3013
- Serveur : 51.15.225.121 (ssh alexis)

## Docs

Detailed docs in `docs/`:
- `installation.md` — setup et dépendances
- `gmail-oauth-setup.md` — configuration OAuth Gmail multi-comptes
- `google-service-account-setup.md` — setup service account Google
