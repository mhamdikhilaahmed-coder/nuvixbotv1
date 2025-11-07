
# Nuvix Tickets — Render Edition (Nebula-style)

**Language:** English • **Theme:** Classic Blue • **Brand:** Nuvix Tickets  
Zero `.env` — everything comes from **Render Environment Variables**.

## ✔ Features
- Nebula-style **panel** with categories: Support, Purchase, Replace, Report
- **Slash commands:** `/setup`, `/panel`, `/ticket open|close|claim|add|remove|rename`, `/transcript`, `/blacklist add|remove|list`, `/review stats`, `/stats`, `/help`, `/ping`
- **DM rating on close** (1–5 stars) with logs to the reviews channel + saved to `data/reviews.json`
- **Transcripts** to channel and file
- **Logs** for command use and ticket events
- **Local storage** in `data/` (JSON files)
- **audioop shim** so it runs on Python 3.12/3.13 without extra packages

## 🔧 Render Environment Variables

Required:
- `NUVIX_TICKETS_TOKEN` — Discord Bot Token
- `GUILD_ID` — Server ID
- `TICKET_CATEGORY_ID` — Category for ticket channels

Logs & DM rating (optional but recommended):
- `LOGS_CMD_USE_CHANNEL_ID`
- `TICKETS_LOGS_CHANNEL_ID`
- `PRIVATE_BOT_LOGS_CHANNEL_ID`
- `TRANSCRIPTS_CHANNEL_ID`
- `REVIEWS_CHANNEL_ID`

Branding (optional):
- `BANNER_URL` — (used on panel/top image)
- `ICON_URL` — (used as author icon)
- `FOOTER_TEXT` — footer text override

Roles (comma-separated IDs):
- `OWNER_ROLE_IDS`
- `COOWNER_ROLE_IDS`
- `STAFF_ROLE_IDS`

Storage:
- `DATA_DIR` (default: `data`)

## 🚀 Deploy on Render
1. Create a **Web Service** (Python).
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `python bot.py`
4. Add the Environment Variables above.
5. Deploy.

> The bot does not open a web port (it is a worker). Configure as a **Background Worker** if preferred.

## ℹ Notes
- The bot registers a **persistent panel view**, so you can press buttons after restart.
- Only **staff** (as per `STAFF_ROLE_IDS` or server admins) can manage tickets (`claim/add/remove/rename/close`).  
  Blacklist is **owner/co-owner only**.  
- `/setup` is **owner/co-owner only** and writes into `data/config.json`.
