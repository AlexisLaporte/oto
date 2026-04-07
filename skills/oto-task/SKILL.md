---
name: oto-task
description: Create tasks, reminders, and calendar events. Use when the user asks to remember something, schedule a task, add a reminder, or create a calendar event.
---

# Task Management (oto google calendar)

Create tasks and reminders via Google Calendar events.

Always pass `-a otomata` (default account).

## Create a task / reminder

```bash
# All-day task (just a date)
oto google calendar create "Task title" -d 2026-04-08 -a otomata

# With description
oto google calendar create "Task title" -d 2026-04-08 --desc "Details here" -a otomata

# Timed event
oto google calendar create "Meeting" -d 2026-04-08T14:00:00 -a otomata

# With end time
oto google calendar create "Meeting" -d 2026-04-08T14:00:00 -e 2026-04-08T15:30:00 -a otomata

# With location
oto google calendar create "Lunch" -d 2026-04-08T12:00:00 -l "Restaurant XYZ" -a otomata
```

## Browse existing events

```bash
# Today
oto google calendar today -a otomata

# Next 7 days
oto google calendar upcoming -a otomata

# Search
oto google calendar search "keyword" -a otomata
```

## Guidelines

- When the user says "rappelle-moi", "ajoute une tâche", "note pour demain", etc. → create an all-day event
- When the user specifies a time → create a timed event
- Convert relative dates ("demain", "lundi prochain") to absolute YYYY-MM-DD
- Keep titles concise, put details in `--desc`
