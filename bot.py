# ==============================
# Nuvix Tickets — Render Edition (Nebula-style)
# ==============================
# • No .env — uses Render environment variables.
# • Audio shim for Python 3.12/3.13 (discord.py imports audioop).
# • Slash commands (English): /setup, /panel, /ticket open|close|claim|add|remove|rename, 
#   /transcript, /blacklist add|remove|list, /review stats, /stats, /help, /ping
# • Panel categories & flow like Nebula (Support / Purchase / Replace / Report).
# • DM rating (1–5 stars) when closing tickets; logs to reviews channel + local JSON.
# • Logs for commands and ticket events.
# • Persistent JSON storage in ./data
# • Works on Render with Python 3.12+.

# ---- audioop shim (avoid ImportError on 3.12/3.13) ----
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **k: None, mul=lambda *a, **k: None, bias=lambda *a, **k: None,
        avg=lambda *a, **k: 0, max=lambda *a, **k: 0, minmax=lambda *a, **k: (0, 0),
        rms=lambda *a, **k: 0, cross=lambda *a, **k: 0, reverse=lambda *a, **k: b"",
        tostereo=lambda *a, **k: b"", tomono=lambda *a, **k: b"",
    )

# ---- std libs ----
import os, io, json, asyncio, datetime as dt
from typing import List, Dict, Any, Optional

# ---- discord.py ----
import discord
from discord import app_commands
from discord.ext import commands

# ============ ENV VARS (Render) ============
NAME = "Nuvix Tickets"  # branding
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")
if not TOKEN:
    raise RuntimeError("NUVIX_TICKETS_TOKEN is not set")

GUILD_ID                = int(os.environ.get("GUILD_ID", "0"))
TICKET_CATEGORY_ID      = int(os.environ.get("TICKET_CATEGORY_ID", "0"))
LOGS_CMD_USE_CHANNEL_ID = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_ID     = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID  = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID      = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))

# Optional styling/env
BANNER_URL  = os.environ.get("BANNER_URL", "")
ICON_URL    = os.environ.get("ICON_URL", "")
FOOTER_TEXT = os.environ.get("FOOTER_TEXT", f"{NAME} • Your wishes, more cheap!")

# Roles: CSV list (staff can manage tickets)
def parse_ids(key: str) -> List[int]:
    raw = os.environ.get(key, "")
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out

OWNER_ROLE_IDS   = parse_ids("OWNER_ROLE_IDS")
COOWNER_ROLE_IDS = parse_ids("COOWNER_ROLE_IDS")
STAFF_ROLE_IDS   = parse_ids("STAFF_ROLE_IDS")

# ============ STORAGE ============
DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)
PATH_CFG  = os.path.join(DATA_DIR, "config.json")
PATH_BL   = os.path.join(DATA_DIR, "blacklist.json")
PATH_REV  = os.path.join(DATA_DIR, "reviews.json")

def _load_json(path: str, default: Any):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: str, data: Any):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# bootstrap files
if not os.path.exists(PATH_CFG):
    _save_json(PATH_CFG, {
        "guild_id": GUILD_ID,
        "ticket_category_id": TICKET_CATEGORY_ID,
        "logs_cmd_use_channel_id": LOGS_CMD_USE_CHANNEL_ID,
        "tickets_logs_channel_id": TICKETS_LOGS_CHANNEL_ID,
        "private_bot_logs_channel_id": PRIVATE_BOT_LOGS_ID,
        "transcripts_channel_id": TRANSCRIPTS_CHANNEL_ID,
        "reviews_channel_id": REVIEWS_CHANNEL_ID,
        "banner_url": BANNER_URL,
        "icon_url": ICON_URL,
        "footer_text": FOOTER_TEXT,
        "staff_role_ids": STAFF_ROLE_IDS,
    })
if not os.path.exists(PATH_BL):
    _save_json(PATH_BL, {"users": []})
if not os.path.exists(PATH_REV):
    _save_json(PATH_REV, {"ratings": []})

# ============ DISCORD CLIENT ============
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
TREE = bot.tree

# Blue classic
COLOR = discord.Color.blue()

def now_str():
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

async def send_safe(channel_id: int, **kwargs):
    if not channel_id:
        return
    ch = bot.get_channel(channel_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(channel_id)
        except Exception:
            return
    try:
        await ch.send(**kwargs)
    except Exception:
        pass

def is_admin(member: discord.Member) -> bool:
    return any(r.permissions.administrator for r in member.roles)

def has_staff(member: discord.Member) -> bool:
    if is_admin(member): return True
    staff_ids = set(STAFF_ROLE_IDS)
    return any(r.id in staff_ids for r in member.roles)

def has_owner_or_coowner(member: discord.Member) -> bool:
    ids = {*(OWNER_ROLE_IDS or []), *(COOWNER_ROLE_IDS or [])}
    return any(r.id in ids for r in member.roles) or is_admin(member)

# ============ PANEL (Nebula-style) ============
CATEGORIES = [
    {"custom_id": "support", "label": "Support",  "emoji": "🎟️", "desc": "Get help from staff"},
    {"custom_id": "purchase", "label": "Purchase", "emoji": "💳", "desc": "Questions about purchases"},
    {"custom_id": "replace", "label": "Replace",  "emoji": "🧾", "desc": "Request a replacement"},
    {"custom_id": "report",  "label": "Report",   "emoji": "⚠️", "desc": "Report issues or users"},
]

class OpenTicketModal(discord.ui.Modal, title="Open Ticket"):
    def __init__(self, category_key: str):
        super().__init__()
        self.category_key = category_key
        self.subject = discord.ui.TextInput(label="Subject", placeholder="Brief subject", max_length=100)
        self.details = discord.ui.TextInput(label="Details", style=discord.TextStyle.long, placeholder="Tell us more...", required=False, max_length=1000)
        self.add_item(self.subject)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        # Check blacklist
        bl = _load_json(PATH_BL, {"users": []})
        if interaction.user.id in bl.get("users", []):
            return await interaction.response.send_message("You are blacklisted from creating tickets.", ephemeral=True)

        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message("Ticket category not configured.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
        }
        # Allow staff
        for rid in STAFF_ROLE_IDS:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        # Admin roles
        for r in interaction.user.roles:
            if r.permissions.administrator:
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

        chan_name = f"{self.category_key}-{interaction.user.name[:20]}"
        try:
            ch = await guild.create_text_channel(
                name=chan_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user} ({interaction.user.id}) [{self.category_key}]",
            )
        except Exception as e:
            return await interaction.response.send_message(f"Failed to create channel: {e}", ephemeral=True)

        # Welcome embed
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Ticket",
            description=f"**Category:** `{self.category_key.title()}`\\n**Subject:** {self.subject.value}\\n\\nA staff member will assist you shortly.\\nYou can use `/ticket close` when done.",
            color=COLOR,
        )
        if ICON_URL:
            embed.set_author(name=f"{NAME}", icon_url=ICON_URL)
        if BANNER_URL:
            embed.set_image(url=BANNER_URL)
        embed.set_footer(text=f"{FOOTER_TEXT} • opened {now_str()}")
        await ch.send(content=interaction.user.mention, embed=embed)

        await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)

        await send_safe(TICKETS_LOGS_CHANNEL_ID,
                        content=f"🆕 Ticket {ch.mention} opened by **{interaction.user}** (`{interaction.user.id}`) — Category **{self.category_key}** — Subject: **{self.subject.value}**")

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for c in CATEGORIES:
            self.add_item(PanelButton(c))

class PanelButton(discord.ui.Button):
    def __init__(self, cat):
        super().__init__(style=discord.ButtonStyle.primary, label=cat["label"], emoji=cat["emoji"], custom_id=f"panel_{cat['custom_id']}")
        self.category_key = cat["custom_id"]

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OpenTicketModal(self.category_key))

# ============ TRANSCRIPT ============
async def build_transcript(channel: discord.TextChannel) -> discord.File:
    lines = []
    async for m in channel.history(limit=2000, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        who = f"{m.author} ({m.author.id})"
        content = (m.content or "").replace("\\n", "\\\\n")
        content = m.content.replace("\\n", "\\\\n") if m.content else ""
        lines.append(f"[{ts}] {who}: {content}")
        for a in m.attachments:
            lines.append(f"  [attachment] {a.filename} -> {a.url}")
    text = "\\n".join(lines) if lines else "No messages."
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.txt")

# ============ RATING (DM) ============
class RatingView(discord.ui.View):
    def __init__(self, channel_name: str):
        super().__init__(timeout=120)
        self.channel_name = channel_name
        for i in range(1, 6):
            self.add_item(RateButton(i, self.channel_name))

class RateButton(discord.ui.Button):
    def __init__(self, stars: int, channel_name: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=f"{stars} ⭐", custom_id=f"rate_{stars}")
        self.stars = stars
        self.channel_name = channel_name

    async def callback(self, interaction: discord.Interaction):
        data = _load_json(PATH_REV, {"ratings": []})
        data["ratings"].append({
            "user_id": interaction.user.id,
            "stars": self.stars,
            "ticket": self.channel_name,
            "ts": now_str(),
        })
        _save_json(PATH_REV, data)
        await interaction.response.send_message(f"Thanks! You rated **{self.stars}** ⭐", ephemeral=True)
        await send_safe(REVIEWS_CHANNEL_ID,
                        content=f"⭐ **Rating:** {self.stars} by **{interaction.user}** (`{interaction.user.id}`) for ticket `{self.channel_name}`")

# ============ EVENTS ============
@bot.event
async def on_ready():
    bot.add_view(PanelView())  # persistent
    try:
        if GUILD_ID:
            await TREE.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await TREE.sync()
    except Exception:
        pass
    await send_safe(PRIVATE_BOT_LOGS_ID, content=f"✅ **{NAME}** online — {now_str()}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="tickets • /panel"))
    print(f"{NAME} is online!")

# ============ COMMANDS ============
@TREE.command(name="ping", description="Check if the bot is alive.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)
    await send_safe(LOGS_CMD_USE_CHANNEL_ID, content=f"🧪 /ping by {interaction.user} (`{interaction.user.id}`)")

@TREE.command(name="help", description="Show help menu.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title=f"{NAME} — Help", color=COLOR, description=(
        "• `/panel` — Post the ticket panel (Nebula-style)\\n"
        "• `/ticket open <subject>` — Open a ticket manually\\n"
        "• `/ticket close [reason]` — Close current ticket, DM rating + transcript\\n"
        "• `/ticket claim` — Mark yourself as handling the ticket\\n"
        "• `/ticket add <@user>` — Give a user access\\n"
        "• `/ticket remove <@user>` — Remove access\\n"
        "• `/ticket rename <new-name>` — Rename ticket\\n"
        "• `/transcript` — Generate and send transcript\\n"
        "• `/blacklist add/remove/list` — Manage blacklist\\n"
        "• `/review stats` — Aggregate ratings\\n"
        "• `/stats` — Basic bot stats\\n"
        "• `/setup` — Configure (owner/co-owner only)"
    ))
    if ICON_URL:
        embed.set_author(name=NAME, icon_url=ICON_URL)
    if BANNER_URL:
        embed.set_image(url=BANNER_URL)
    embed.set_footer(text=f"{FOOTER_TEXT}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@TREE.command(name="panel", description="Post the Nebula-style ticket panel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{NAME} — Ticket Panel",
        description="**Select a ticket category**\\nChoose the option that best fits your request.",
        color=COLOR,
    )
    if ICON_URL:
        embed.set_author(name=NAME, icon_url=ICON_URL)
    if BANNER_URL:
        embed.set_image(url=BANNER_URL)
    embed.set_footer(text=FOOTER_TEXT)

    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)
    await send_safe(LOGS_CMD_USE_CHANNEL_ID, content=f"📌 /panel posted by {interaction.user} (`{interaction.user.id}`) in {interaction.channel.mention}")

ticket = app_commands.Group(name="ticket", description="Ticket commands")

@ticket.command(name="open", description="Open a ticket (manual).")
async def ticket_open(interaction: discord.Interaction, subject: str):
    modal = OpenTicketModal("support")
    modal.subject.default = subject[:100]
    await interaction.response.send_modal(modal)

def is_ticket_channel(ch: discord.abc.GuildChannel) -> bool:
    return isinstance(ch, discord.TextChannel) and (not TICKET_CATEGORY_ID or ch.category_id == TICKET_CATEGORY_ID)

@ticket.command(name="close", description="Close the current ticket.")
async def ticket_close(interaction: discord.Interaction, reason: Optional[str] = "No reason provided"):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)

    file = await build_transcript(interaction.channel)
    await send_safe(TRANSCRIPTS_CHANNEL_ID,
                    content=f"🧾 Transcript for {interaction.channel.mention} — closed by **{interaction.user}** — Reason: {reason}",
                    file=file)

    opener = None
    async for m in interaction.channel.history(limit=50, oldest_first=True):
        if not m.author.bot:
            opener = m.author
            break
    if opener:
        try:
            embed = discord.Embed(
                title="Rate your ticket",
                description=(
                    f"Your ticket **{interaction.channel.name}** has been closed.\\n"
                    f"**Reason:** {reason}\\n\\n"
                    "How would you rate your experience?"
                ),
                color=COLOR,
            )
            if ICON_URL:
                embed.set_author(name=NAME, icon_url=ICON_URL)
            embed.set_footer(text=FOOTER_TEXT)
            await opener.send(embed=embed, view=RatingView(interaction.channel.name))
        except Exception:
            pass

    await send_safe(TICKETS_LOGS_CHANNEL_ID,
                    content=f"🔒 Ticket `{interaction.channel.name}` closed by **{interaction.user}** — Reason: {reason}")

    try:
        await interaction.channel.delete(reason=f"Closed by {interaction.user} — {reason}")
    except Exception as e:
        return await interaction.response.send_message(f"Failed to delete channel: {e}", ephemeral=True)

    await interaction.response.send_message("Ticket closed.", ephemeral=True)

@ticket.command(name="claim", description="Claim the current ticket (staff only).")
async def ticket_claim(interaction: discord.Interaction):
    if not has_staff(interaction.user):
        return await interaction.response.send_message("You don't have permission.", ephemeral=True)
    ch = interaction.channel
    if not is_ticket_channel(ch):
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    await ch.edit(name=f"{ch.name}-claimed")
    await ch.send(f"{interaction.user.mention} has claimed this ticket.")
    await interaction.response.send_message("Claimed.", ephemeral=True)

@ticket.command(name="add", description="Add a user to the ticket (staff only).")
async def ticket_add(interaction: discord.Interaction, user: discord.Member):
    if not has_staff(interaction.user):
        return await interaction.response.send_message("You don't have permission.", ephemeral=True)
    ch = interaction.channel
    if not is_ticket_channel(ch):
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    await ch.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
    await ch.send(f"{user.mention} was added by {interaction.user.mention}.")
    await interaction.response.send_message("User added.", ephemeral=True)

@ticket.command(name="remove", description="Remove a user from the ticket (staff only).")
async def ticket_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_staff(interaction.user):
        return await interaction.response.send_message("You don't have permission.", ephemeral=True)
    ch = interaction.channel
    if not is_ticket_channel(ch):
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    await ch.set_permissions(user, overwrite=None)
    await ch.send(f"{user.mention} was removed by {interaction.user.mention}.")
    await interaction.response.send_message("User removed.", ephemeral=True)

@ticket.command(name="rename", description="Rename the ticket (staff only).")
async def ticket_rename(interaction: discord.Interaction, new_name: str):
    if not has_staff(interaction.user):
        return await interaction.response.send_message("You don't have permission.", ephemeral=True)
    ch = interaction.channel
    if not is_ticket_channel(ch):
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    try:
        await ch.edit(name=new_name[:90])
        await interaction.response.send_message("Renamed.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Rename failed: {e}", ephemeral=True)

TREE.add_command(ticket)

# ---- transcript command ----
@TREE.command(name="transcript", description="Generate and send transcript for this ticket.")
async def transcript_cmd(interaction: discord.Interaction):
    ch = interaction.channel
    if not is_ticket_channel(ch):
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    file = await build_transcript(ch)
    await interaction.response.send_message("Transcript generated.", ephemeral=True)
    await send_safe(TRANSCRIPTS_CHANNEL_ID, content=f"🧾 Transcript for {ch.mention}", file=file)

# ---- blacklist ----
blacklist = app_commands.Group(name="blacklist", description="Blacklist management")

@blacklist.command(name="add", description="Add a user to blacklist (owner/co-owner only).")
async def bl_add(interaction: discord.Interaction, user: discord.Member):
    if not has_owner_or_coowner(interaction.user):
        return await interaction.response.send_message("Owner/Co-owner only.", ephemeral=True)
    data = _load_json(PATH_BL, {"users": []})
    if user.id not in data["users"]:
        data["users"].append(user.id)
        _save_json(PATH_BL, data)
    await interaction.response.send_message(f"User {user} added to blacklist.", ephemeral=True)

@blacklist.command(name="remove", description="Remove a user from blacklist (owner/co-owner only).")
async def bl_remove(interaction: discord.Interaction, user: discord.Member):
    if not has_owner_or_coowner(interaction.user):
        return await interaction.response.send_message("Owner/Co-owner only.", ephemeral=True)
    data = _load_json(PATH_BL, {"users": []})
    if user.id in data["users"]:
        data["users"].remove(user.id)
        _save_json(PATH_BL, data)
    await interaction.response.send_message(f"User {user} removed from blacklist.", ephemeral=True)

@blacklist.command(name="list", description="List blacklisted users.")
async def bl_list(interaction: discord.Interaction):
    data = _load_json(PATH_BL, {"users": []})
    ids = data.get("users", [])
    if not ids:
        return await interaction.response.send_message("Blacklist is empty.", ephemeral=True)
    text = "\\n".join([f"• <@{i}> ({i})" for i in ids])
    await interaction.response.send_message(f"Blacklisted users:\\n{text}", ephemeral=True)

TREE.add_command(blacklist)

# ---- review ----
review = app_commands.Group(name="review", description="Review system")

@review.command(name="stats", description="Show rating stats.")
async def review_stats(interaction: discord.Interaction):
    data = _load_json(PATH_REV, {"ratings": []})
    r = data.get("ratings", [])
    if not r:
        return await interaction.response.send_message("No ratings yet.", ephemeral=True)
    avg = sum(x["stars"] for x in r) / len(r)
    embed = discord.Embed(title="Review Stats", color=COLOR, description=f"**Total reviews:** {len(r)}\\n**Average:** {avg:.2f} ⭐")
    await interaction.response.send_message(embed=embed, ephemeral=True)

TREE.add_command(review)

# ---- stats ----
@TREE.command(name="stats", description="Show basic bot stats.")
async def stats_cmd(interaction: discord.Interaction):
    g = interaction.guild
    if not g:
        return await interaction.response.send_message("Use in a server.", ephemeral=True)
    cats = sum(1 for c in g.categories)
    chans = sum(1 for c in g.channels)
    roles = len(g.roles)
    embed = discord.Embed(title=f"{NAME} — Stats", color=discord.Color.blue(),
                          description=f"Guild: **{g.name}**\\nChannels: **{chans}**\\nCategories: **{cats}**\\nRoles: **{roles}**")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- setup ----
@TREE.command(name="setup", description="Configure IDs and settings (owner/co-owner only).")
async def setup_cmd(interaction: discord.Interaction,
                    ticket_category_id: Optional[str]=None,
                    logs_cmd_use_channel_id: Optional[str]=None,
                    tickets_logs_channel_id: Optional[str]=None,
                    transcripts_channel_id: Optional[str]=None,
                    reviews_channel_id: Optional[str]=None):
    if not has_owner_or_coowner(interaction.user):
        return await interaction.response.send_message("Owner/Co-owner only.", ephemeral=True)

    cfg = _load_json(PATH_CFG, {})
    def fix(v): 
        try: return int(v) if v else None
        except: return None

    if ticket_category_id:       cfg["ticket_category_id"]       = fix(ticket_category_id) or cfg.get("ticket_category_id")
    if logs_cmd_use_channel_id:  cfg["logs_cmd_use_channel_id"]  = fix(logs_cmd_use_channel_id) or cfg.get("logs_cmd_use_channel_id")
    if tickets_logs_channel_id:  cfg["tickets_logs_channel_id"]  = fix(tickets_logs_channel_id) or cfg.get("tickets_logs_channel_id")
    if transcripts_channel_id:   cfg["transcripts_channel_id"]   = fix(transcripts_channel_id) or cfg.get("transcripts_channel_id")
    if reviews_channel_id:       cfg["reviews_channel_id"]       = fix(reviews_channel_id) or cfg.get("reviews_channel_id")
    _save_json(PATH_CFG, cfg)

    await interaction.response.send_message("Setup updated.", ephemeral=True)

# ============ RUN ============
bot.run(TOKEN)

# --- Keep Alive HTTP server (for Render Web Service) ---
from threading import Thread
from flask import Flask

app = Flask('keep_alive')

@app.route('/')
def home():
    return "Nuvix Tickets is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()
