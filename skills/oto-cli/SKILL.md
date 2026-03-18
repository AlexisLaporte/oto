---
name: oto-cli
description: "Otomata CLI tools: anthropic costs, enrichment (Kaspr/Hunter/Lemlist), Notion, Pennylane accounting, SIRENE/company data. Use for any `oto` command not covered by oto-browser/google/search/whatsapp."
---

# Otomata CLI (oto)

`oto` est installé globalement via pipx. Pas de venv, taper directement `oto <commande>`.

---

## Anthropic — Usage & Coûts

```bash
oto anthropic usage                          # 7 derniers jours, groupé par modèle
oto anthropic usage --days 30 --bucket 1d --group-by model
oto anthropic cost                           # coûts 30 derniers jours
oto anthropic cost --days 60 --group-by workspace_id
oto anthropic summary --days 7               # résumé quotidien avec coûts estimés
oto anthropic today                          # coût d'aujourd'hui
```

---

## Enrichissement contacts

### Kaspr (LinkedIn → email/téléphone)

```bash
oto enrichment kaspr enrich "john-doe-123abc"
oto enrichment kaspr enrich "john-doe-123abc" --name "John Doe"
```

### Hunter (emails par domaine)

```bash
oto enrichment hunter domain "example.com" -n 10
oto enrichment hunter find "example.com" --name "John Doe"
oto enrichment hunter verify "john@example.com"
```

### Lemlist (campagnes outreach)

```bash
oto enrichment lemlist campaigns
oto enrichment lemlist leads CAMPAIGN_ID
oto enrichment lemlist add-lead CAMPAIGN_ID -e "email" --first-name "X" --last-name "Y" --company "Z"
oto enrichment lemlist delete-lead CAMPAIGN_ID "email"
oto enrichment lemlist export CAMPAIGN_ID
```

---

## Notion

```bash
oto notion search "query"
oto notion search "query" --filter-type page|database
oto notion page PAGE_ID [--blocks]
oto notion database DATABASE_ID [--query --limit 50]
```

---

## Pennylane — Comptabilité

```bash
oto pennylane company                        # info société
oto pennylane fiscal-years
oto pennylane trial-balance --start 2025-01-01 --end 2025-12-31
oto pennylane ledger-accounts                # plan comptable
oto pennylane customer-invoices --max-pages 50
oto pennylane supplier-invoices --max-pages 50
oto pennylane categories
oto pennylane complete --year 2025           # export complet annuel
```

---

## SIRENE & Entreprises

### Recherche

```bash
oto sirene search "otomata" -n 20
oto sirene search --naf "6201Z,6202A" -n 50
oto sirene search --dept "75" --city "Paris" -n 30
oto sirene search "conseil" --naf "7022Z" --dept "69" -n 10
oto sirene entreprises "fintech" --naf "6201Z" --dept "75" --ca-min 100000 -n 25
```

### Détail

```bash
oto sirene get 123456789           # par SIREN
oto sirene siret 12345678900001    # par SIRET
oto sirene headquarters 123456789  # siège social
oto company info 123456789         # dirigeants, finances
oto sirene suggest-naf "développement SaaS" -n 3
```
