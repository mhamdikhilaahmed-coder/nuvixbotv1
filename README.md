# Nuvix Tickets (Render-ready)

**Features**
- Works on Render with Python 3.12/3.13
- No `.env` usage (reads only from Render Environment Variables)
- Slash commands: `/ping`, `/ticket open`, `/ticket close`
- Logs to channels (optional)
- Transcript as TXT on close

## Environment Variables (Render)

Required:
- `NUVIX_TICKETS_TOKEN` — your bot token.
- `GUILD_ID` — guild ID where to sync commands.
- `TICKET_CATEGORY_ID` — category ID where tickets will be created.

Optional (recommended):
- `LOGS_CMD_USE_CHANNEL_ID` — channel to record command use.
- `TICKETS_LOGS_CHANNEL_ID` — ticket lifecycle logs.
- `PRIVATE_BOT_LOGS_CHANNEL_ID` — bot internal "online" pings.
- `TRANSCRIPTS_CHANNEL_ID` — transcripts uploads.
- `REVIEWS_CHANNEL_ID` — reserved for future reviews.
- `STAFF_ROLE_IDS` — comma-separated role IDs who can view/handle tickets.

## Deploy on Render

1. Set **Python** as environment.
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `python bot.py`
4. Set the variables listed above.
5. Deploy.

The project includes an `audioop` shim (`nuvix_patch.py`) to avoid crashes with discord.py.
