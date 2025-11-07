# Nuvix Tickets — Render Edition (Nebula-style)
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **k: None, mul=lambda *a, **k: None,
        bias=lambda *a, **k: None, avg=lambda *a, **k: 0,
        max=lambda *a, **k: 0, minmax=lambda *a, **k: (0,0),
        rms=lambda *a, **k: 0, cross=lambda *a, **k: 0,
        reverse=lambda *a, **k: b"", tostereo=lambda *a, **k: b"",
        tomono=lambda *a, **k: b"",
    )
import os, asyncio, datetime as dt
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import run as keep_alive_run
from util_transcript import build_text_transcript, build_html_transcript
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")
if not TOKEN: raise RuntimeError("NUVIX_TICKETS_TOKEN is not set")
GUILD_ID = int(os.environ.get("GUILD_ID", "0"))
BOT_NAME = os.environ.get("BOT_NAME", "Nuvix Tickets")
ICON_URL = os.environ.get("ICON_URL", "")
BANNER_URL = os.environ.get("BANNER_URL", "")
FOOTER_TEXT = os.environ.get("FOOTER_TEXT", "Nuvix • Your wishes, more cheap!")
try: THEME_COLOR = int(os.environ.get("THEME_COLOR", str(discord.Color.blurple().value)))
except Exception: THEME_COLOR = discord.Color.blurple().value
STAFF_ROLE_IDS = [int(x) for x in os.environ.get("STAFF_ROLE_IDS","").split(",") if x.strip().isdigit()]
OWNER_ROLE_IDS = [int(x) for x in os.environ.get("OWNER_ROLE_IDS","").split(",") if x.strip().isdigit()]
COOWNER_ROLE_IDS = [int(x) for x in os.environ.get("COOWNER_ROLE_IDS","").split(",") if x.strip().isdigit()]
TICKET_CATEGORY_ID = int(os.environ.get("TICKET_CATEGORY_ID", "0"))
SALES_CATEGORY_ID = int(os.environ.get("SALES_CATEGORY_ID", str(TICKET_CATEGORY_ID)))
SUPPORT_CATEGORY_ID = int(os.environ.get("SUPPORT_CATEGORY_ID", str(TICKET_CATEGORY_ID)))
PARTNERS_CATEGORY_ID = int(os.environ.get("PARTNERS_CATEGORY_ID", str(TICKET_CATEGORY_ID)))
BILLING_CATEGORY_ID = int(os.environ.get("BILLING_CATEGORY_ID", str(TICKET_CATEGORY_ID)))
LOGS_CMD_USE_CHANNEL_ID = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))
def now_text():
    try: return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception: return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
def is_staff(m: discord.Member) -> bool:
    if m.guild_permissions.administrator: return True
    have = {r.id for r in m.roles}; return any(rid in have for rid in (STAFF_ROLE_IDS+OWNER_ROLE_IDS+COOWNER_ROLE_IDS))
async def send_safe(cid: int, **kw):
    if not cid: return
    ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
    try: await ch.send(**kw)
    except Exception: pass
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
class TicketPanel(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Sales", style=discord.ButtonStyle.primary, custom_id="nuvix_sales")
    async def sales(self, itx, _): await open_ticket(itx, "Sales", SALES_CATEGORY_ID)
    @discord.ui.button(label="Support", style=discord.ButtonStyle.primary, custom_id="nuvix_support")
    async def support(self, itx, _): await open_ticket(itx, "Support", SUPPORT_CATEGORY_ID)
    @discord.ui.button(label="Partners", style=discord.ButtonStyle.primary, custom_id="nuvix_partners")
    async def partners(self, itx, _): await open_ticket(itx, "Partners", PARTNERS_CATEGORY_ID)
    @discord.ui.button(label="Billing", style=discord.ButtonStyle.primary, custom_id="nuvix_billing")
    async def billing(self, itx, _): await open_ticket(itx, "Billing", BILLING_CATEGORY_ID)
async def build_overwrites(guild, opener):
    ow = { guild.default_role: discord.PermissionOverwrite(view_channel=False),
           opener: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True) }
    for rid in STAFF_ROLE_IDS+OWNER_ROLE_IDS+COOWNER_ROLE_IDS:
        role = guild.get_role(rid)
        if role: ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, manage_channels=True)
    return ow
async def open_ticket(itx: discord.Interaction, subject: str, category_id: int):
    await itx.response.defer(ephemeral=True, thinking=False)
    guild = itx.guild
    if guild is None: return await itx.followup.send("Use this inside a server.", ephemeral=True)
    cat = guild.get_channel(category_id or TICKET_CATEGORY_ID)
    if not isinstance(cat, discord.CategoryChannel): return await itx.followup.send("Ticket category is not configured.", ephemeral=True)
    ow = await build_overwrites(guild, itx.user)
    name = f"ticket-{itx.user.name[:20]}"
    ch = await guild.create_text_channel(name=name, category=cat, overwrites=ow, reason=f"Ticket by {itx.user}")
    e = discord.Embed(title="🎫 New Ticket",
        description=(f"**Subject:** {subject}\n**Opened by:** {itx.user.mention}\n\n"
                     "Please provide **details** so our team can assist you faster:\n"
                     "• What do you need?\n• Order/Invoice or proof (if applicable)\n• Screenshots or error messages\n"),
        color=THEME_COLOR)
    if ICON_URL: e.set_thumbnail(url=ICON_URL)
    if BANNER_URL: e.set_image(url=BANNER_URL)
    e.set_footer(text=f"{FOOTER_TEXT} • {now_text()}")
    ctl = discord.Embed(title="Ticket Controls",
        description=("Use these commands:\n"
                     "`/ticket claim` • `/ticket add` • `/ticket remove` • `/ticket rename`\n"
                     "`/ticket transcript` • `/ticket close`\n"), color=THEME_COLOR)
    await ch.send(content=itx.user.mention, embeds=[e, ctl])
    await itx.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)
    await send_safe(TICKETS_LOGS_CHANNEL_ID, content=f"🆕 Ticket {ch.mention} opened by {itx.user.mention} ({itx.user.id}) — **{subject}**")
@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else: await tree.sync()
        print("✅ Commands synced successfully")
    except Exception as e: print(f"⚠️ Command sync failed: {e}")
    await send_safe(PRIVATE_BOT_LOGS_CHANNEL_ID, content=f"✅ **{BOT_NAME}** is online — {now_text()}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="tickets • /panel"))
ticket = app_commands.Group(name="ticket", description="Ticket commands")
admin = app_commands.Group(name="admin", description="Admin commands")
reviews = app_commands.Group(name="reviews", description="Reviews commands")
transcripts = app_commands.Group(name="transcripts", description="Transcripts commands")
@tree.command(name="panel", description="Send the ticket panel (Nebula style)")
@app_commands.checks.has_any_role(*STAFF_ROLE_IDS) if STAFF_ROLE_IDS else (lambda f: f)
async def panel_cmd(itx: discord.Interaction, title: str="Nuvix Tickets", subtitle: str="Select a ticket category"):
    await itx.response.defer(ephemeral=True)
    e = discord.Embed(title=title, description=subtitle, color=THEME_COLOR)
    if ICON_URL: e.set_thumbnail(url=ICON_URL)
    if BANNER_URL: e.set_image(url=BANNER_URL)
    e.set_footer(text=FOOTER_TEXT)
    await itx.channel.send(embed=e, view=TicketPanel())
    await itx.followup.send("Ticket panel sent.", ephemeral=True)
    await send_safe(LOGS_CMD_USE_CHANNEL_ID, content=f"📌 /panel by {itx.user.mention} in {itx.channel.mention}")
@ticket.command(name="open", description="Open a new ticket manually")
async def ticket_open(itx: discord.Interaction, subject: str="General"):
    await open_ticket(itx, subject=subject, category_id=TICKET_CATEGORY_ID)
@ticket.command(name="close", description="Close this ticket (transcript + review)")
async def ticket_close(itx: discord.Interaction, reason: str="No reason provided"):
    await itx.response.defer(ephemeral=True)
    ch = itx.channel
    if not isinstance(ch, discord.TextChannel): return await itx.followup.send("Use inside a ticket channel.", ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("You need Staff to close tickets.", ephemeral=True)
    txt = await build_text_transcript(ch); html = await build_html_transcript(ch)
    await send_safe(TRANSCRIPTS_CHANNEL_ID, content=f"🧾 Transcript for {ch.mention} — closed by {itx.user.mention} — Reason: {reason}", file=txt)
    await send_safe(TRANSCRIPTS_CHANNEL_ID, file=html)
    await send_safe(TICKETS_LOGS_CHANNEL_ID, content=f"🔒 {ch.mention} closed by {itx.user.mention} — Reason: {reason}")
    opener=None
    async for m in ch.history(limit=50, oldest_first=True):
        if not m.author.bot: opener=m.author; break
    if opener:
        try:
            dm = await opener.create_dm()
            e = discord.Embed(title="Your ticket has been closed",
                description=f"Channel: **#{ch.name}**\\nReason: **{reason}**\\n\\nPlease rate our support from **1 to 5 stars** and optionally add a comment.",
                color=THEME_COLOR)
            if ICON_URL: e.set_thumbnail(url=ICON_URL)
            await dm.send(embed=e); await dm.send("Reply with a number **1-5** for your rating. You may also add a short comment in the same message.")
        except Exception: pass
    try: await ch.delete(reason=f"Closed by {itx.user} — {reason}")
    except Exception as e: return await itx.followup.send(f"Failed to delete channel: {e}", ephemeral=True)
    await itx.followup.send("Ticket closed.", ephemeral=True)
@ticket.command(name="transcript", description="Create a transcript for this ticket")
async def ticket_transcript(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    ch = itx.channel
    if not isinstance(ch, discord.TextChannel): return await itx.followup.send("Use inside a ticket channel.", ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    txt = await build_text_transcript(ch); html = await build_html_transcript(ch)
    await itx.followup.send("Transcript generated.", ephemeral=True)
    await send_safe(TRANSCRIPTS_CHANNEL_ID, content=f"🧾 Manual transcript for {ch.mention} — by {itx.user.mention}", file=txt)
    await send_safe(TRANSCRIPTS_CHANNEL_ID, file=html)
@ticket.command(name="claim", description="Claim this ticket")
async def ticket_claim(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if isinstance(ch, discord.TextChannel):
        await ch.send(f"✅ {itx.user.mention} **claimed** this ticket.")
        await itx.followup.send("Claimed.", ephemeral=True)
@ticket.command(name="unclaim", description="Unclaim this ticket")
async def ticket_unclaim(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if isinstance(ch, discord.TextChannel):
        await ch.send(f"⛔ {itx.user.mention} **unclaimed** this ticket.")
        await itx.followup.send("Unclaimed.", ephemeral=True)
@ticket.command(name="add", description="Add a user to this ticket")
async def ticket_add(itx: discord.Interaction, user: discord.User):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if not isinstance(ch, discord.TextChannel): return await itx.followup.send("Use inside a ticket.", ephemeral=True)
    try:
        await ch.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await ch.send(f"➕ {user.mention} was added by {itx.user.mention}."); await itx.followup.send("User added.", ephemeral=True)
    except Exception as e: await itx.followup.send(f"Failed: {e}", ephemeral=True)
@ticket.command(name="remove", description="Remove a user from this ticket")
async def ticket_remove(itx: discord.Interaction, user: discord.User):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if not isinstance(ch, discord.TextChannel): return await itx.followup.send("Use inside a ticket.", ephemeral=True)
    try:
        await ch.set_permissions(user, overwrite=None)
        await ch.send(f"➖ {user.mention} was removed by {itx.user.mention}."); await itx.followup.send("User removed.", ephemeral=True)
    except Exception as e: await itx.followup.send(f"Failed: {e}", ephemeral=True)
@ticket.command(name="rename", description="Rename this ticket channel")
async def ticket_rename(itx: discord.Interaction, new_name: str):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.edit(name=new_name[:95]); await ch.send(f"✏️ Renamed by {itx.user.mention} → **#{new_name}**"); await itx.followup.send("Renamed.", ephemeral=True)
        except Exception as e: await itx.followup.send(f"Failed: {e}", ephemeral=True)
@ticket.command(name="alert", description="Send a closing soon alert")
async def ticket_alert(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel
    if isinstance(ch, discord.TextChannel):
        await ch.send("⏰ This ticket will be closed soon if there is no response."); await itx.followup.send("Alert sent.", ephemeral=True)
@ticket.command(name="changecategory", description="Move this ticket to another category")
async def ticket_changecategory(itx: discord.Interaction, category_id: int):
    await itx.response.defer(ephemeral=True)
    if not is_staff(itx.user): return await itx.followup.send("Staff only.", ephemeral=True)
    ch = itx.channel; guild = itx.guild; cat = guild.get_channel(category_id) if guild else None
    if isinstance(ch, discord.TextChannel) and isinstance(cat, discord.CategoryChannel):
        await ch.edit(category=cat); await ch.send(f"📦 Moved to **{cat.name}** by {itx.user.mention}."); await itx.followup.send("Moved.", ephemeral=True)
    else: await itx.followup.send("Invalid category.", ephemeral=True)
@ticket.command(name="delete", description="Delete this ticket immediately (Admin)")
async def ticket_delete(itx: discord.Interaction, reason: str="No reason"):
    await itx.response.defer(ephemeral=True)
    if not itx.user.guild_permissions.administrator: return await itx.followup.send("Admin only.", ephemeral=True)
    ch = itx.channel
    if isinstance(ch, discord.TextChannel):
        try: await ch.delete(reason=f"Deleted by {itx.user} — {reason}")
        except Exception as e: return await itx.followup.send(f"Failed: {e}", ephemeral=True)
        await send_safe(TICKETS_LOGS_CHANNEL_ID, content=f"🗑️ Ticket deleted by {itx.user.mention} — Reason: {reason}")
tree.add_command(ticket)
@admin.command(name="settings", description="Show current configuration")
async def admin_settings(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    e = discord.Embed(title="Configuration", color=THEME_COLOR, description="Current environment-based settings.")
    e.add_field(name="Guild", value=str(GUILD_ID)); e.add_field(name="Theme Color", value=str(THEME_COLOR))
    e.add_field(name="Staff Roles", value=", ".join(map(str, STAFF_ROLE_IDS)) or "None", inline=False)
    e.add_field(name="Ticket Cats", value=f"Sales:{SALES_CATEGORY_ID} Support:{SUPPORT_CATEGORY_ID} Partners:{PARTNERS_CATEGORY_ID} Billing:{BILLING_CATEGORY_ID}", inline=False)
    e.add_field(name="Logs", value=f"CMD:{LOGS_CMD_USE_CHANNEL_ID} TICKETS:{TICKETS_LOGS_CHANNEL_ID} PRIVATE:{PRIVATE_BOT_LOGS_CHANNEL_ID}", inline=False)
    e.add_field(name="Transcripts/Reviews", value=f"TRANSCRIPTS:{TRANSCRIPTS_CHANNEL_ID} REVIEWS:{REVIEWS_CHANNEL_ID}", inline=False)
    await itx.followup.send(embed=e, ephemeral=True)
@admin.command(name="sync", description="Force sync slash commands")
async def admin_sync(itx: discord.Interaction):
    await itx.response.defer(ephemeral=True)
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else: await tree.sync()
        await itx.followup.send("✅ Commands synced.", ephemeral=True)
    except Exception as e: await itx.followup.send(f"Failed: {e}", ephemeral=True)
@admin.command(name="stats", description="Show ticket stats (simple)")
async def admin_stats(itx: discord.Interaction):
    await itx.response.send_message("Tickets online. (Simple stats placeholder)", ephemeral=True)
tree.add_command(admin)
@reviews.command(name="list", description="List recent reviews")
async def reviews_list(itx: discord.Interaction):
    await itx.response.send_message("Reviews list will appear in the Reviews channel.", ephemeral=True)
@reviews.command(name="stats", description="Show average rating")
async def reviews_stats(itx: discord.Interaction):
    await itx.response.send_message("Average: N/A (no DB). Ratings are pushed to the Reviews channel.", ephemeral=True)
tree.add_command(reviews)
@transcripts.command(name="list", description="List recent transcripts")
async def transcripts_list(itx: discord.Interaction):
    await itx.response.send_message("Check the Transcripts channel for files.", ephemeral=True)
@transcripts.command(name="view", description="(Placeholder) View a transcript by ticket ID")
async def transcripts_view(itx: discord.Interaction, ticket_id: str):
    await itx.response.send_message(f"Use search in the Transcripts channel for `{ticket_id}`.", ephemeral=True)
tree.add_command(transcripts)
@tree.command(name="ping", description="Check bot latency")
async def ping_cmd(itx: discord.Interaction):
    await itx.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True); await send_safe(LOGS_CMD_USE_CHANNEL_ID, content=f"🧪 /ping by {itx.user.mention}")
@tree.command(name="help", description="Show help")
async def help_cmd(itx: discord.Interaction):
    await itx.response.send_message("Use `/panel` to create tickets and `/ticket close` to finish.", ephemeral=True)
@tree.command(name="info", description="Bot information")
async def info_cmd(itx: discord.Interaction):
    e = discord.Embed(title=BOT_NAME, description="Nuvix Tickets • Nebula-style", color=THEME_COLOR)
    if ICON_URL: e.set_thumbnail(url=ICON_URL)
    if BANNER_URL: e.set_image(url=BANNER_URL)
    e.set_footer(text=FOOTER_TEXT)
    await itx.response.send_message(embed=e, ephemeral=True)
async def main():
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, keep_alive_run)
    await bot.start(TOKEN)
if __name__ == "__main__":
    asyncio.run(main())
