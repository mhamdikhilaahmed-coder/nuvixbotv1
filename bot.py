# ==============================
# Nuvix Tickets — Render Web Service
# ==============================
# - English text (Nebula-style).
# - Classic blue theme.
# - 4 ticket categories via panel (Support / Purchases / Not Received / Replace).
# - Staff-only controls (assign / close / add / remove).
# - HTML transcript to Transcripts channel + DM to user.
# - Review request via DM (1–5 stars + optional comment) to Reviews channel.
# - Blacklist, basic staff stats (placeholders), help, sync, priority tag.
# - Auto-sync on startup (guild if provided, else global).
# - Keepalive Flask server (optional) for Render Web Service 24/7.

from __future__ import annotations

# ---------- Patch audioop for Python 3.12+/3.13 -----------
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **kw: None,
        mul=lambda *a, **kw: None,
        bias=lambda *a, **kw: None,
        avg=lambda *a, **kw: 0,
        max=lambda *a, **kw: 0,
        minmax=lambda *a, **kw: (0, 0),
        rms=lambda *a, **kw: 0,
        cross=lambda *a, **kw: 0,
        reverse=lambda *a, **kw: b"",
        tostereo=lambda *a, **kw: b"",
        tomono=lambda *a, **kw: b"",
    )

# -------------------- Imports --------------------
import os
import io
import json
import traceback
import datetime as dt
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands

# -------------------- Keepalive (Render Web) --------------------
# Enable by setting KEEPALIVE=1 (Render expects a port to be bound).
KEEPALIVE = os.getenv("KEEPALIVE", "0") == "1"
_app = None
if KEEPALIVE:
    from flask import Flask, jsonify
    _app = Flask(__name__)

    @_app.get("/")
    def _root():
        return jsonify(ok=True, service="nuvix-tickets")

    def run_keepalive():
        port = int(os.getenv("PORT", "10000"))
        # host 0.0.0.0 mandatory in Render
        _app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# -------------------- Environment --------------------
TOKEN = os.getenv("NUVIX_TICKETS_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("❌ Missing NUVIX_TICKETS_TOKEN/TOKEN environment variable.")

# Guild-scoped sync (faster updates). If 0, global sync.
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# Logging channels
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.getenv("PRIVATE_BOT_LOGS_CHANNEL_ID", "0") or 0)
LOGS_CMD_USE_CHANNEL_ID     = int(os.getenv("LOGS_CMD_USE_CHANNEL_ID", "0") or 0)
TICKETS_LOGS_CHANNEL_ID     = int(os.getenv("TICKETS_LOGS_CHANNEL_ID", "0") or 0)
TRANSCRIPTS_CHANNEL_ID      = int(os.getenv("TRANSCRIPTS_CHANNEL_ID", "0") or 0)
REVIEWS_CHANNEL_ID          = int(os.getenv("REVIEWS_CHANNEL_ID", "0") or 0)

# Branding
BOT_NAME   = os.getenv("BOT_NAME", "Nuvix Tickets")
ICON_URL   = os.getenv("ICON_URL", "")  # server icon / avatar
BANNER_URL = os.getenv("BANNER_URL", "")  # decorative
FOOTER_TEXT = os.getenv("FOOTER_TEXT", "Nuvix • Your wishes, more cheap!")
# Parse hex color (e.g. "0x5865F2")
THEME_COLOR = int(os.getenv("THEME_COLOR", "0x5865F2"), 16)

# Owners & staff
OWNER_ID   = int(os.getenv("OWNER_ID", "0") or 0)
COOWNER_ID = int(os.getenv("COOWNER_ID", "0") or 0)
STAFF_ROLE_IDS = []
_raw_staff = os.getenv("STAFF_ROLE_IDS", "")
if _raw_staff:
    for p in _raw_staff.split(","):
        p = p.strip()
        if p.isdigit():
            STAFF_ROLE_IDS.append(int(p))

# Categories (defaults: TICKET_CATEGORY_ID if specific missing)
TICKET_CATEGORY_ID        = int(os.getenv("TICKET_CATEGORY_ID", "0") or 0)
PURCHASES_CATEGORY_ID     = int(os.getenv("PURCHASES_CATEGORY_ID", "0") or 0)
NOT_RECEIVED_CATEGORY_ID  = int(os.getenv("NOT_RECEIVED_CATEGORY_ID", "0") or 0)
REPLACE_CATEGORY_ID       = int(os.getenv("REPLACE_CATEGORY_ID", "0") or 0)
SUPPORT_CATEGORY_ID       = int(os.getenv("SUPPORT_CATEGORY_ID", "0") or 0)

# ─────────────────────────────────────────────────────────────────────────────
# Intents & Bot
class NuvixBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
        )

    async def setup_hook(self) -> None:
        # Sincroniza los slash commands automáticamente al iniciar
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            synced = await self.tree.sync(guild=guild)
            print(f"[AUTO SYNC] {len(synced)} comandos sincronizados en guild {GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"[AUTO SYNC] {len(synced)} comandos sincronizados globalmente")

        # Mantén persistentes las vistas (botones/panel)
        self.add_view(TicketPanelView())

        # Estado dinámico: muestra cuántos tickets hay abiertos
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len([c for c in self.get_all_channels() if 'ticket' in c.name])} tickets abiertos"
        ))

# -------------------- Helper Functions --------------------
def now_utc_str() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    staff_ids = {r.id for r in member.roles}
    return any(rid in staff_ids for rid in STAFF_ROLE_IDS)

def make_embed(title: str, description: str = "", color: Optional[int] = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color or THEME_COLOR)
    if ICON_URL:
        e.set_author(name=BOT_NAME, icon_url=ICON_URL)
    else:
        e.set_author(name=BOT_NAME)
    if BANNER_URL:
        e.set_thumbnail(url=BANNER_URL)
    e.set_footer(text=FOOTER_TEXT)
    return e

async def log_to(channel_id: int, *, embed: Optional[discord.Embed] = None, content: Optional[str] = None, file: Optional[discord.File] = None):
    if not channel_id:
        return
    ch = bot.get_channel(channel_id)
    if isinstance(ch, (discord.TextChannel, discord.Thread)):
        await ch.send(content=content, embed=embed, file=file)

async def get_category(guild: discord.Guild, kind: str) -> Optional[discord.CategoryChannel]:
    mapping = {
        "purchases": PURCHASES_CATEGORY_ID,
        "not_received": NOT_RECEIVED_CATEGORY_ID,
        "replace": REPLACE_CATEGORY_ID,
        "support": SUPPORT_CATEGORY_ID,
    }
    cid = mapping.get(kind, 0) or TICKET_CATEGORY_ID
    return guild.get_channel(cid) if cid else None

# -------------------- Blacklist (persist to file) --------------------
BLACKLIST_PATH = "blacklist.json"
try:
    with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
        _data = json.load(f)
        BLACKLIST = set(int(x) for x in _data)
except Exception:
    BLACKLIST = set()

def save_blacklist():
    try:
        with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
            json.dump(list(BLACKLIST), f)
    except Exception:
        pass

# -------------------- Ticket Panel (Nebula-like) --------------------
class PurchasesModal(discord.ui.Modal, title="Purchases"):
    item = discord.ui.TextInput(
        label="What do you want to buy?",
        placeholder="Describe the product or service you want to purchase",
        required=True,
        max_length=200,
    )
    amount = discord.ui.TextInput(
        label="Quantity",
        placeholder="How many units?",
        required=True,
        max_length=50,
    )
    method = discord.ui.TextInput(
        label="Payment method",
        placeholder="Which payment method will you use?",
        required=True,
        max_length=100,
    )

    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "purchases", self.opener, {
            "What do you want to buy?": str(self.item),
            "Quantity": str(self.amount),
            "Payment method": str(self.method),
        })

class NotReceivedModal(discord.ui.Modal, title="Product not received"):
    invoice = discord.ui.TextInput(
        label="Invoice ID",
        placeholder="Paste your invoice ID",
        required=True,
        max_length=100,
    )
    pay_method = discord.ui.TextInput(
        label="Payment method used",
        placeholder="Which method did you use to pay?",
        required=True,
        max_length=120,
    )
    pay_date = discord.ui.TextInput(
        label="Payment date",
        placeholder="When did you make the payment? (YYYY-MM-DD)",
        required=True,
        max_length=50,
    )

    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "not_received", self.opener, {
            "Invoice ID": str(self.invoice),
            "Payment method used": str(self.pay_method),
            "Payment date": str(self.pay_date),
        })

class ReplaceModal(discord.ui.Modal, title="Replace"):
    purchase_type = discord.ui.TextInput(
        label="Is it a store purchase or a replacement?",
        placeholder="New purchase or replacement of an old item/account?",
        required=True,
        max_length=200,
    )
    order_or_invoice = discord.ui.TextInput(
        label="Invoice or Order ID",
        placeholder="Provide invoice or replacement order ID",
        required=True,
        max_length=120,
    )
    issue = discord.ui.TextInput(
        label="Describe the issue",
        placeholder="Explain the problem in detail",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "replace", self.opener, {
            "Purchase vs Replacement": str(self.purchase_type),
            "Invoice/Order ID": str(self.order_or_invoice),
            "Issue": str(self.issue),
        })

class SupportModal(discord.ui.Modal, title="Support"):
    help_text = discord.ui.TextInput(
        label="How can we help you?",
        placeholder="Briefly describe your request",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "support", self.opener, {
            "Request": str(self.help_text),
        })

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", style=discord.ButtonStyle.blurple, emoji="🎟️", custom_id="nuvix:support")
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SupportModal(interaction.user))

    @discord.ui.button(label="Purchases", style=discord.ButtonStyle.blurple, emoji="🛒", custom_id="nuvix:purchases")
    async def btn_purchases(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PurchasesModal(interaction.user))

    @discord.ui.button(label="Not Received", style=discord.ButtonStyle.blurple, emoji="⚠️", custom_id="nuvix:notreceived")
    async def btn_notreceived(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NotReceivedModal(interaction.user))

    @discord.ui.button(label="Replace", style=discord.ButtonStyle.gray, emoji="🧾", custom_id="nuvix:replace")
    async def btn_replace(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplaceModal(interaction.user))

# -------------------- Ticket creation & controls --------------------
async def create_ticket(
    interaction: discord.Interaction,
    kind: str,
    opener: discord.Member,
    fields: Dict[str, str],
):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True)
        return

    if opener.id in BLACKLIST:
        await interaction.response.send_message("You are blacklisted from creating tickets.", ephemeral=True)
        return

    cat = await get_category(guild, kind)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True, attach_files=True, embed_links=True
        ),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=True, manage_messages=True
            )

    prefix = {
        "support": "supp-",
        "purchases": "purch-",
        "not_received": "nrcv-",
        "replace": "repl-",
    }.get(kind, "ticket-")

    channel_name = f"{prefix}{opener.name}".lower()
    ch = await guild.create_text_channel(
        name=channel_name,
        category=cat,
        overwrites=overwrites,
        reason=f"Ticket opened by {opener} ({kind})",
    )

    title_map = {
        "support": "Support Ticket",
        "purchases": "Purchases Ticket",
        "not_received": "Product not received",
        "replace": "Replace Ticket",
    }
    e = make_embed(title_map.get(kind, "Support Ticket"))
    e.description = (
        "Please wait until one of our support team members can help you.\n"
        "**Response time may vary due to many factors, so please be patient.**"
    )
    # Assigned staff field starts empty
    e.add_field(name="Assigned staff", value="*(none yet)*", inline=False)
    # Form details
    details = "\n".join(f"**{k}:** {v}" for k, v in fields.items()) or "*No data*"
    e.add_field(name="Form Details", value=details, inline=False)

    await ch.send(content=opener.mention, embed=e, view=TicketControlsView())

    await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)
    await log_to(TICKETS_LOGS_CHANNEL_ID, embed=make_embed("Ticket Created", f"**Type:** {kind}\n**User:** {opener.mention}\n**Channel:** {ch.mention}"))

class TicketControlsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Assign me", style=discord.ButtonStyle.success, emoji="👋", custom_id="nuvix:assign")
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            await interaction.response.send_message("Only staff can assign.", ephemeral=True)
            return
        await assign_staff(interaction, interaction.user)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="nuvix:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            await interaction.response.send_message("Only staff can close.", ephemeral=True)
            return
        await close_ticket(interaction)

# -------------------- Transcript & Review --------------------
async def render_transcript_html(channel: discord.TextChannel) -> bytes:
    msgs = [m async for m in channel.history(limit=1000, oldest_first=True)]
    out = []
    for m in msgs:
        ts = m.created_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = discord.utils.escape_markdown(m.author.display_name)
        content = discord.utils.escape_markdown(m.content or "")
        out.append(f"<p><b>[{ts}] {author}:</b> {content}</p>")
        # add attachments
        for a in m.attachments:
            out.append(f"<p style='margin-left:1rem'><i>Attachment:</i> <a href='{a.url}' target='_blank'>{a.filename}</a></p>")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Transcript - {channel.name}</title></head>
<body style="font-family: system-ui, Arial; color:#222">
<h2>Transcript — {channel.guild.name} / #{channel.name}</h2>
{' '.join(out) if out else '<p><i>No messages</i></p>'}
</body></html>"""
    return html.encode("utf-8")

async def send_review_request(user: discord.User, ticket_channel: discord.TextChannel):
    try:
        dm = await user.create_dm()

        class StarsSelect(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(label="⭐ 1", value="1"),
                    discord.SelectOption(label="⭐⭐ 2", value="2"),
                    discord.SelectOption(label="⭐⭐⭐ 3", value="3"),
                    discord.SelectOption(label="⭐⭐⭐⭐ 4", value="4"),
                    discord.SelectOption(label="⭐⭐⭐⭐⭐ 5", value="5"),
                ]
                super().__init__(placeholder="Rate your support (1–5 stars)", options=options, min_values=1, max_values=1, custom_id="nuvix:review:stars")

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.send_modal(ReviewModal(self.values[0]))

        class ReviewModal(discord.ui.Modal, title="Leave a review"):
            extra = discord.ui.TextInput(
                label="Anything you want to add?",
                placeholder="Optional comment",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000,
            )
            def __init__(self, stars: str):
                super().__init__(timeout=600)
                self.stars = stars

            async def on_submit(self, interaction: discord.Interaction):
                stars = int(self.stars)
                comment = str(self.extra).strip() if self.extra else ""
                emb = make_embed("New Ticket Review")
                emb.add_field(name="Stars", value=f"{'⭐'*stars} ({stars}/5)", inline=False)
                emb.add_field(name="User", value=interaction.user.mention, inline=True)
                emb.add_field(name="Ticket", value=ticket_channel.mention, inline=True)
                if comment:
                    emb.add_field(name="Comment", value=comment, inline=False)
                await log_to(REVIEWS_CHANNEL_ID, embed=emb)
                await interaction.response.send_message("Thanks! Your review has been submitted.", ephemeral=True)

        view = discord.ui.View(timeout=600)
        view.add_item(StarsSelect())
        e = make_embed("How was your support?", "Please rate your ticket experience and add an optional comment.")
        await dm.send(embed=e, view=view)
    except Exception:
        pass

async def close_ticket(interaction: discord.Interaction):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)

    # Try to find ticket opener (first non-bot mention in first bot message)
    opener: Optional[discord.Member] = None
    async for m in ch.history(limit=30, oldest_first=True):
        if m.mentions:
            opener = m.mentions[0]
            break

    # Transcript
    data = await render_transcript_html(ch)
    file = discord.File(io.BytesIO(data), filename=f"{ch.name}-transcript.html")

    # Send transcript to Transcripts channel
    await log_to(TRANSCRIPTS_CHANNEL_ID, content=f"Transcript for {ch.mention}", file=file)

    # DM transcript + review form
    if opener:
        try:
            dm = await opener.create_dm()
            await dm.send(content=f"Your ticket **#{ch.name}** has been closed. Here is your transcript:", file=file)
            await send_review_request(opener, ch)
        except Exception:
            pass

    await log_to(TICKETS_LOGS_CHANNEL_ID, embed=make_embed("Ticket Closed", f"Channel: {ch.mention}\nBy: {interaction.user.mention}"))
    await interaction.response.send_message("Closing ticket…", ephemeral=True)
    try:
        await ch.delete(reason=f"Closed by {interaction.user}")
    except discord.Forbidden:
        await interaction.followup.send("I couldn't delete the channel (missing permissions).", ephemeral=True)

async def assign_staff(interaction: discord.Interaction, member: discord.Member):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)

    # Find first bot embed in the ticket channel
    base_msg = None
    async for m in ch.history(limit=50, oldest_first=True):
        if m.author == bot.user and m.embeds:
            base_msg = m
            break

    if base_msg and base_msg.embeds:
        e = base_msg.embeds[0]
        # Rebuild to preserve theme/footer/author
        new = make_embed(e.title or "Support Ticket", e.description or "")
        # Keep fields except "Assigned staff"
        for f in e.fields:
            if f.name.lower().startswith("assigned"):
                continue
            new.add_field(name=f.name, value=f.value, inline=f.inline)
        new.add_field(name="Assigned staff", value=member.mention, inline=False)
        await base_msg.edit(embed=new)

    await interaction.response.send_message(f"Assigned to {member.mention}.", ephemeral=True)

# -------------------- Checks --------------------
def staff_only():
    async def predicate(interaction: discord.Interaction):
        return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)
    return app_commands.check(predicate)

def owner_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.id in {OWNER_ID, COOWNER_ID}
    return app_commands.check(predicate)

# Crear el bot primero
bot = NuvixBot()

# ────────────────────────────────────────────────
# Slash commands
# ────────────────────────────────────────────────

@bot.tree.command(name="ping", description="Check bot latency (Pong!)")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! `{round(bot.latency*1000)}ms`", ephemeral=True)

@bot.tree.command(name="panel", description="Post the ticket panel")
@staff_only()
async def cmd_panel(interaction: discord.Interaction):
    e = make_embed("Nuvix Tickets — Ticket Panel", "Select a ticket category and submit the form.")
    await interaction.response.send_message(embed=e, view=TicketPanelView())
    await log_to(LOGS_CMD_USE_CHANNEL_ID, embed=make_embed("/panel", f"By {interaction.user.mention} in {interaction.channel.mention}"))

@bot.tree.command(name="assign", description="Assign the current ticket to a staff member")
@staff_only()
@app_commands.describe(member="Staff member to assign")
async def cmd_assign(interaction: discord.Interaction, member: discord.Member):
    await assign_staff(interaction, member)

@bot.tree.command(name="unassign", description="Remove the assigned staff from header")
@staff_only()
async def cmd_unassign(interaction: discord.Interaction):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    base_msg = None
    async for m in ch.history(limit=50, oldest_first=True):
        if m.author == bot.user and m.embeds:
            base_msg = m
            break
    if base_msg and base_msg.embeds:
        e = base_msg.embeds[0]
        new = make_embed(e.title or "Support Ticket", e.description or "")
        for f in e.fields:
            if f.name.lower().startswith("assigned"):
                continue
            new.add_field(name=f.name, value=f.value, inline=f.inline)
        await base_msg.edit(embed=new)
    await interaction.response.send_message("Unassigned.", ephemeral=True)

@bot.tree.command(name="add", description="Add a user to this ticket")
@staff_only()
@app_commands.describe(user="User to add")
async def cmd_add(interaction: discord.Interaction, user: discord.Member):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    await ch.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"Added {user.mention}.", ephemeral=True)

@bot.tree.command(name="remove", description="Remove a user from this ticket")
@staff_only()
@app_commands.describe(user="User to remove")
async def cmd_remove(interaction: discord.Interaction, user: discord.Member):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    await ch.set_permissions(user, overwrite=None)
    await interaction.response.send_message(f"Removed {user.mention}.", ephemeral=True)

@bot.tree.command(name="close", description="Close the current ticket (staff only)")
@staff_only()
async def cmd_close(interaction: discord.Interaction):
    await close_ticket(interaction)

@bot.tree.command(name="transcript", description="Generate transcript (HTML) and post in the channel")
@staff_only()
async def cmd_transcript(interaction: discord.Interaction):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    data = await render_transcript_html(ch)
    file = discord.File(io.BytesIO(data), filename=f"{ch.name}-transcript.html")
    await interaction.response.send_message("Transcript generated (see file below).", ephemeral=True)
    await ch.send(file=file)

@bot.tree.command(name="ticket_priority", description="Set a priority tag in the channel topic")
@staff_only()
@app_commands.describe(level="Priority level")
@app_commands.choices(level=[
    app_commands.Choice(name="low", value="low"),
    app_commands.Choice(name="normal", value="normal"),
    app_commands.Choice(name="high", value="high"),
    app_commands.Choice(name="critical", value="critical"),
])
async def cmd_priority(interaction: discord.Interaction, level: app_commands.Choice[str]):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    topic = ch.topic or ""
    for tag in ("[P:low]", "[P:normal]", "[P:high]", "[P:critical]"):
        topic = topic.replace(tag, "")
    topic = f"{topic} [P:{level.value}]".strip()
    await ch.edit(topic=topic)
    await interaction.response.send_message(f"Priority set to **{level.value}**.", ephemeral=True)

@bot.tree.command(name="blacklist", description="Manage ticket blacklist")
@staff_only()
@app_commands.describe(action="add/remove/list", user="Target user (add/remove)")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="list", value="list"),
])
async def cmd_blacklist(interaction: discord.Interaction, action: app_commands.Choice[str], user: Optional[discord.Member] = None):
    act = action.value
    if act in {"add", "remove"} and user is None:
        await interaction.response.send_message("Specify a user.", ephemeral=True)
        return
    if act == "add":
        BLACKLIST.add(user.id)
        save_blacklist()
        await interaction.response.send_message(f"Blacklisted {user.mention}.", ephemeral=True)
    elif act == "remove":
        BLACKLIST.discard(user.id)
        save_blacklist()
        await interaction.response.send_message(f"Removed {user.mention} from blacklist.", ephemeral=True)
    else:
        if not BLACKLIST:
            await interaction.response.send_message("Blacklist is empty.", ephemeral=True)
        else:
            txt = "\n".join(f"- <@{uid}>" for uid in BLACKLIST)
            await interaction.response.send_message(f"Blacklisted users:\n{txt}", ephemeral=True)

# Staff stats (placeholders; ready to be wired to DB if you want)
@bot.tree.command(name="staffstats_me", description="View your support stats")
@staff_only()
async def cmd_staffstats_me(interaction: discord.Interaction):
    await interaction.response.send_message("Tickets today: 0 • Tickets this month: 0 • Total: 0 (placeholder)", ephemeral=True)

@bot.tree.command(name="staffstats_user", description="View another staff member stats")
@staff_only()
@app_commands.describe(user="Staff member")
async def cmd_staffstats_user(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.mention} — Tickets today: 0 • Tickets this month: 0 • Total: 0 (placeholder)", ephemeral=True)

@bot.tree.command(name="staffstats_leaderboard", description="View staff leaderboard")
@staff_only()
async def cmd_staffstats_leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message("Leaderboard coming soon (placeholder).", ephemeral=True)

@bot.tree.command(name="staffstats_monthclaims", description="Show staff with N claims this month")
@staff_only()
@app_commands.describe(count="Minimum claims")
async def cmd_staffstats_monthclaims(interaction: discord.Interaction, count: int = 5):
    await interaction.response.send_message(f"Staff with ≥{count} claims this month (placeholder).", ephemeral=True)

@bot.tree.command(name="help", description="List of commands")
async def cmd_help(interaction: discord.Interaction):
    lines = [
        "**Panel & Ticket**",
        "`/panel` — Post the ticket panel",
        "`/assign [member]` • `/unassign`",
        "`/add [user]` • `/remove [user]`",
        "`/close` • `/transcript`",
        "`/ticket_priority [low|normal|high|critical]`",
        "",
        "**Moderation**",
        "`/blacklist add|remove|list [user]`",
        "",
        "**Stats (placeholders)**",
        "`/staffstats_me` • `/staffstats_user [member]`",
        "`/staffstats_leaderboard` • `/staffstats_monthclaims [count]`",
        "",
        "**Utils**",
        "`/ping` • `/sync` (owner only)",
    ]
    e = make_embed("Nuvix Tickets — Help", "\n".join(lines))
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="sync", description="Sync application commands (owner only)")
@owner_only()
async def cmd_sync(interaction: discord.Interaction):
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        await interaction.response.send_message(f"Synced {len(synced)} commands to guild `{GUILD_ID}`.", ephemeral=True)
    else:
        synced = await bot.tree.sync()
        await interaction.response.send_message(f"Globally synced {len(synced)} commands.", ephemeral=True)

# -------------------- Events --------------------
@bot.event
async def on_ready():
    # Persist button handlers across restarts
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlsView())

    # Auto-sync on startup (guild if provided, else global)
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            print(f"[SYNC] Registered {len(synced)} commands for guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"[SYNC] Registered {len(synced)} global commands")
    except Exception as e:
        print("[SYNC ERROR]", e)

    print(f"[READY] Logged in as {bot.user} | {now_utc_str()}")
    await log_to(PRIVATE_BOT_LOGS_CHANNEL_ID, embed=make_embed(f"{BOT_NAME} online", f"— {now_utc_str()}"))

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    await log_to(LOGS_CMD_USE_CHANNEL_ID, embed=make_embed("Command used", f"`/{command.name}` by {interaction.user.mention} in {interaction.channel.mention}"))

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    print(tb)

# ─────────────────────────────────────────────────────────────────────────────
# FORCE SYNC DE COMANDOS
# ─────────────────────────────────────────────────────────────────────────────
import asyncio

async def force_sync():
    await bot.wait_until_ready()
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"[FORCE SYNC] {len(synced)} comandos sincronizados en guild {GUILD_ID}")
    else:
        synced = await bot.tree.sync()
        print(f"[FORCE SYNC] {len(synced)} comandos sincronizados globalmente")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN + KEEPALIVE
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if KEEPALIVE:
        from threading import Thread
        Thread(target=run_flask, daemon=True).start()

    bot = NuvixBot()
    bot.run(TOKEN)
