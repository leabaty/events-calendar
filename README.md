# Events Gap

Automatic pipeline that reads local event newsletters from Gmail, extracts event details using domain-specific HTML parsers, and inserts them into a dedicated Google Calendar called **"Events Gap"**.

## How it works

```
Gmail (label: events-gap)
    │
    ▼
gmail_reader.py ─── OAuth2 → fetch unread emails
    │
    ▼
parser.py ───────── BeautifulSoup + regex → extract events from HTML
    │                  (walpine.fr / basp05.com / cimalpes.fr + generic)
    ▼
calendar_writer.py ── Service Account → create events in Google Calendar
    │
    ▼
Emails labelled "events-gap/traité" (not reprocessed)
```

## Project structure

```
events-gap/
├── .github/workflows/
│   └── fetch_events.yml      # Daily cron (08:00 UTC)
├── src/
│   ├── main.py               # Orchestrator
│   ├── gmail_reader.py       # Gmail API — read & label emails
│   ├── parser.py             # Event extraction (per-domain + generic)
│   └── calendar_writer.py    # Google Calendar API — create events
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup

### 1. Gmail API — OAuth2 token

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Gmail API**
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `client_secret_*.json`
5. Run the provided `get_token.py` script locally to generate `token.json`:

```bash
python get_token.py
```

This will open a browser for the OAuth consent flow. After success, a `token.json` file is created containing a `refresh_token`.

6. The content of `token.json` will be stored as a GitHub Secret named `GMAIL_TOKEN`.

### 2. Google Calendar — Service Account

1. In the same (or another) Google Cloud project, create a **Service Account**
2. Download its JSON key
3. Enable the **Google Calendar API**
4. Share your **"Events Gap"** calendar with the service account email (as **Make changes to events**)
5. The content of the JSON key will be stored as a GitHub Secret named `GOOGLE_CALENDAR_CREDENTIALS`
6. The calendar ID is stored as a GitHub Secret named `GOOGLE_CALENDAR_ID`

### 3. Gmail labels

Create these labels in your Gmail:
- `events-gap` — apply manually to any newsletter email you want processed
- `events-gap/traité` — automatically applied by the script after processing

### 4. GitHub Secrets

| Secret | Description |
|---|---|
| `GMAIL_TOKEN` | Content of `token.json` (OAuth2 refresh token) |
| `GOOGLE_CALENDAR_CREDENTIALS` | Content of the service account JSON key |
| `GOOGLE_CALENDAR_ID` | ID of the target Google Calendar |

### 5. Test locally

```bash
pip install -r requirements.txt
export GMAIL_TOKEN="$(cat token.json)"
export GOOGLE_CALENDAR_CREDENTIALS="$(cat service_account.json)"
export GOOGLE_CALENDAR_ID="your-calendar-id@group.calendar.google.com"
python src/main.py
```

## Supported newsletter sources

| Domain | Parser |
|---|---|
| walpine.fr | Custom HTML parser (event cards, headings) |
| basp05.com | Custom HTML parser (tables, div blocks) |
| cimalpes.fr | Custom HTML parser (magazine layout) |
| *Other* | Generic regex-based fallback |

## GitHub Actions

The workflow `fetch_events.yml` runs daily at 08:00 UTC via `cron`. It can also be triggered manually from the Actions tab.
