# Nuvix Tickets — Render Web Service (Nebula-style)

Features
- Nebula-style panel and rich command set (ticket/admin/util/review/transcript groups)
- Per-category buttons (Sales / Support / Partners / Billing)
- HTML + TXT transcripts (sent to Transcripts channel)
- DM review prompt (1–5 stars + comment), forward to Reviews channel
- No `.env`. Uses Render Environment Variables only
- Web Service ping via Flask to keep instance alive

Service Type: Web Service  
Start Command: `python bot.py`

Environment variables: see bot.py header or below.
