---
name: oto-pennylane
description: "Pennylane accounting: invoices, transactions, suppliers, customers, products, quotes, file uploads, matching. Source de vérité compta."
---

# Comptabilité Pennylane (oto pennylane)

Prérequis : `oto` installé (pipx), `PENNYLANE_API_KEY` dans `~/.otomata/secrets.env`.

Pennylane est la **source de vérité comptable** (remplace compta-YYYY.json).

## Commandes lecture

```bash
oto pennylane company                    # Info société
oto pennylane fiscal-years               # Exercices fiscaux
oto pennylane trial-balance --start X --end Y  # Balance
oto pennylane ledger-accounts            # Plan comptable
oto pennylane categories                 # Catégories de dépenses
oto pennylane complete --year 2026       # Dump complet annuel

oto pennylane customer-invoices          # Factures clients
oto pennylane supplier-invoices          # Factures fournisseurs
oto pennylane transactions               # Transactions bancaires
oto pennylane customers                  # Clients
oto pennylane suppliers                  # Fournisseurs
oto pennylane products                   # Produits
```

## Commandes écriture

```bash
# Clients
oto pennylane create-customer "Nom" --email x@y.com --address "..." --postal-code 75009 --city Paris

# Produits
oto pennylane create-product "Prestation IA" --price 700.00 --unit day --vat FR_200

# Factures clients (draft par défaut)
oto pennylane create-invoice -c CUSTOMER_ID -d 2026-03-01 --deadline 2026-03-31 -l PRODUCT_ID:QUANTITY
oto pennylane finalize-invoice INVOICE_ID

# Devis
oto pennylane create-quote -c CUSTOMER_ID -d 2026-03-01 --deadline 2026-03-31 -l PRODUCT_ID:QUANTITY

# Upload PDFs
oto pennylane upload fichier.pdf             # Un fichier
oto pennylane upload-dir admin/compta/2026/achats/  # Tout un dossier

# Rapprochement facture ↔ transaction
oto pennylane match INVOICE_ID TRANSACTION_ID --type supplier   # ou customer
```

## Lignes de facture

Format : `--line product_id:quantity[:unit_price]`
Exemple : `--line 16741024:5 --line 16741024:1:350.00`

## TVA

- Régime : réel normal mensuel (CA3)
- Micro-BNC : TVA exigible à l'**encaissement** (pas à la facturation)
- Codes TVA : `FR_200` (20%), `FR_100` (10%), `FR_55` (5.5%), `exempt`
- Autoliquidation clients hors France : TVA = 0 sur la facture

## Notes

- Les factures clients doivent être finalisées pour être rapprochées
- La finalisation nécessite une numérotation configurée dans Pennylane (Paramètres > Facturation)
- `file_attachment_id` est obligatoire pour `supplier_invoices/import`
- Pagination cursor-based pour transactions (pas page-based)
- PUT `/transactions/{id}/categories` avec `[{"id": cat_id, "weight": "1.0"}]` pour catégoriser
- L'archivage de transactions n'est pas possible via l'API (UI uniquement)
