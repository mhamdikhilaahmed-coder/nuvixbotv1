Nuvix Tickets — Render Edition (Classic Blue)

How to deploy on Render:
1) Create a Python service, start command:  python bot.py
2) Environment variables (all strings unless noted):
   - NUVIX_TICKETS_TOKEN            (string)  -> Bot token
   - GUILD_ID                       (int)     -> Discord server id
   - TICKET_CATEGORY_ID             (int)     -> Category id for tickets
   - LOGS_CMD_USE_CHANNEL_ID        (int)
   - TICKETS_LOGS_CHANNEL_ID        (int)
   - PRIVATE_BOT_LOGS_CHANNEL_ID    (int)
   - TRANSCRIPTS_CHANNEL_ID         (int)
   - REVIEWS_CHANNEL_ID             (int)     -> Optional
   - FOOTER_TEXT                    (string)  -> Footer for embeds
   - STAFF_ROLE_IDS                 (comma separated ints) -> Optional staff roles

Slash commands:
 - /panel (admin only): posts the ticket panel
 - /ping
 - /ticket open <subject>
 - /ticket close [reason]

This build avoids audioop import errors by shimming the module. Voice features are not used.
