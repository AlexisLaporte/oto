---
name: oto-zoho
description: Zoho CRM — contacts, leads, deals, accounts, notes. Use for CRM record management.
---

# Zoho CRM

Use `oto zoho` commands via Bash. All output is JSON.

## Prerequisites

Secrets in `~/.otomata/secrets.env`:
```
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
# Optional (defaults to US data center):
# ZOHO_API_DOMAIN=https://www.zohoapis.eu
# ZOHO_ACCOUNTS_URL=https://accounts.zoho.eu
```

## Commands

```bash
# List available modules
oto zoho modules

# List records (default 20)
oto zoho records Contacts -n 50
oto zoho records Leads -n 10
oto zoho records Deals
oto zoho records Accounts

# Get a single record
oto zoho record Contacts 1234567890

# Search records (Zoho criteria syntax)
oto zoho search Contacts "(Email:equals:john@doe.com)"
oto zoho search Leads "(Company:contains:Acme)"
oto zoho search Deals "(Stage:equals:Closed Won)" -n 50

# Create a record
oto zoho add-record Contacts -f First_Name=John -f Last_Name=Doe -f Email=john@doe.com
oto zoho add-record Leads -f Company=Acme -f Last_Name=Smith -f Email=smith@acme.com

# Update a record
oto zoho update-record Contacts 1234567890 -f Phone=+33612345678
oto zoho update-record Deals 9876543210 -f Stage="Closed Won"

# Delete a record
oto zoho delete-record Contacts 1234567890

# Notes
oto zoho notes Contacts 1234567890
oto zoho add-note Contacts 1234567890 "Call summary" "Discussed pricing, follow up next week"
```

## Search criteria syntax

Format: `(Field_API_Name:operator:value)`. Operators: `equals`, `starts_with`, `contains`.

Combine with `and`/`or`: `((Email:contains:@gmail.com)and(Last_Name:starts_with:D))`

## Common modules

| Module     | API name   | Key fields                              |
|------------|------------|-----------------------------------------|
| Contacts   | Contacts   | First_Name, Last_Name, Email, Phone     |
| Leads      | Leads      | First_Name, Last_Name, Company, Email   |
| Deals      | Deals      | Deal_Name, Stage, Amount, Closing_Date  |
| Accounts   | Accounts   | Account_Name, Website, Industry, Phone  |

Use `oto zoho modules` to discover all available modules.
