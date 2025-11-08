# ==============================
# Nuvix Tickets - Render Version
# ==============================

from __future__ import annotations

# --- Patch for missing audioop (Python 3.12/3.13) ---
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

# --- Imports ---
import os
import io
import datetime as dt
import discord
from discord import app_commands
from discord.ext import commands
from keepalive import run as run_flask


# ─────────────────────────────────────────────────────────────────────────────
# Optional keep-alive (Render Web Service)
KEEPALIVE = os.getenv("KEEPALIVE", "0") == "1"
if KEEPALIVE:
    from threading import Thread
    from flask import Flask

    app = Flask(__name__)

    @app.get("/")
    def _ok():
        return {"ok": True, "service": "nuvix-tickets"}

    def run_flask():
        port = int(os.getenv("PORT", "10000"))
        app.run(host="0.0.0.0", port=port, debug=False)

# ─────────────────────────────────────────────────────────────────────────────
# Environment
TOKEN = os.getenv("NUVIX_TICKETS_TOKEN") or os.getenv("TOKEN")

GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# Logs
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.getenv("PRIVATE_BOT_LOGS_CHANNEL_ID", "0") or 0)
LOGS_CMD_USE_CHANNEL_ID     = int(os.getenv("LOGS_CMD_USE_CHANNEL_ID", "0") or 0)
TICKETS_LOGS_CHANNEL_ID     = int(os.getenv("TICKETS_LOGS_CHANNEL_ID", "0") or 0)
TRANSCRIPTS_CHANNEL_ID      = int(os.getenv("TRANSCRIPTS_CHANNEL_ID", "0") or 0)
REVIEWS_CHANNEL_ID          = int(os.getenv("REVIEWS_CHANNEL_ID", "0") or 0)

# Visuals
BOT_NAME   = os.getenv("BOT_NAME", "Nuvix Tickets")
ICON_URL   = os.getenv("ICON_URL", "")
BANNER_URL = os.getenv("BANNER_URL", "")
FOOTER_TEXT= os.getenv("FOOTER_TEXT", "Nuvix • Your wishes, more cheap!")
THEME_COLOR= int(os.getenv("THEME_COLOR", str(0x5865F2)))  # Classic blue default

# Owners / Staff
OWNER_ID   = int(os.getenv("OWNER_ID", "0") or 0)
COOWNER_ID = int(os.getenv("COOWNER_ID", "0") or 0)
STAFF_ROLE_IDS = []
_raw_staff = os.getenv("STAFF_ROLE_IDS", "")
if _raw_staff:
    for part in _raw_staff.split(","):
        part = part.strip()
        if part.isdigit():
            STAFF_ROLE_IDS.append(int(part))

# Categories (fallback to TICKET_CATEGORY_ID if a specific one is missing)
TICKET_CATEGORY_ID           = int(os.getenv("TICKET_CATEGORY_ID", "0") or 0)
PURCHASES_CATEGORY_ID        = int(os.getenv("PURCHASES_CATEGORY_ID", "0") or 0)
NOT_RECEIVED_CATEGORY_ID     = int(os.getenv("NOT_RECEIVED_CATEGORY_ID", "0") or 0)
REPLACE_CATEGORY_ID          = int(os.getenv("REPLACE_CATEGORY_ID", "0") or 0)
SUPPORT_CATEGORY_ID          = int(os.getenv("SUPPORT_CATEGORY_ID", "0") or 0)

# ─────────────────────────────────────────────────────────────────────────────
# Intents & Bot
intents = discord.Intents.default()  # Slash commands don't need message content
intents.members = True
intents.guilds = True

class NuvixBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            application_id=None,
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            # Sync on startup for the guild only
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"[SYNC] Registered {len(synced)} app commands in guild {GUILD_ID}")

        # Persist views (panel buttons) across restarts
        self.add_view(TicketPanelView())

bot = NuvixBot()

# ─────────────────────────────────────────────────────────────────────────────
# Utilities

def now_utc_str() -> str:
    # discord.py warns about utcnow(); use timezone-aware
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {r.id for r in member.roles}
    return any(rid in ids for rid in STAFF_ROLE_IDS)

async def get_category(guild: discord.Guild, kind: str) -> Optional[discord.CategoryChannel]:
    mapping = {
        "purchases": PURCHASES_CATEGORY_ID,
        "not_received": NOT_RECEIVED_CATEGORY_ID,
        "replace": REPLACE_CATEGORY_ID,
        "support": SUPPORT_CATEGORY_ID,
    }
    target_id = mapping.get(kind, 0) or TICKET_CATEGORY_ID
    if not target_id:
        return None
    return guild.get_channel(target_id)

def make_embed(title: str, description: str = "", color: Optional[int] = None) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=description,
        color=color or THEME_COLOR
    )
    if ICON_URL:
        e.set_author(name=BOT_NAME, icon_url=ICON_URL)
    else:
        e.set_author(name=BOT_NAME)
    if BANNER_URL:
        e.set_thumbnail(url=BANNER_URL)
    e.set_footer(text=FOOTER_TEXT)
    return e

async def log_channel(bot: NuvixBot, channel_id: int, embed: discord.Embed):
    if not channel_id:
        return
    ch = bot.get_channel(channel_id)
    if isinstance(ch, (discord.TextChannel, discord.Thread)):
        await ch.send(embed=embed)

# ─────────────────────────────────────────────────────────────────────────────
# Blacklist (simple in-memory + file persistence)
BLACKLIST_PATH = "blacklist.json"
try:
    with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
        BLACKLIST = set(json.load(f))
except Exception:
    BLACKLIST = set()

def save_blacklist():
    try:
        with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
            json.dump(list(BLACKLIST), f)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Ticket Panel (Buttons -> Modals)

class PurchasesModal(discord.ui.Modal, title="Purchases"):
    item = discord.ui.TextInput(
        label="What do you want buy?",
        placeholder="Describe what you want buy",
        required=True,
        max_length=200
    )
    amount = discord.ui.TextInput(
        label="Amount for buy?",
        placeholder="Enter the quantity of the product you want to",
        required=True,
        max_length=50
    )
    method = discord.ui.TextInput(
        label="Payment Method?",
        placeholder="What payment method do you want to use?",
        required=True,
        max_length=100
    )
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "purchases", self.opener, {
            "What do you want buy?": str(self.item),
            "Amount for buy?": str(self.amount),
            "Payment Method?": str(self.method),
        })

class NotReceivedModal(discord.ui.Modal, title="Product not received"):
    invoice = discord.ui.TextInput(
        label="Invoice id",
        placeholder="Put your invoice id",
        required=True,
        max_length=100
    )
    pay_method = discord.ui.TextInput(
        label="What payment method did you use?",
        placeholder="Describe payment method did you use",
        required=True,
        max_length=200
    )
    pay_date = discord.ui.TextInput(
        label="When you did the payment?",
        placeholder="Put the date about the when did the payment",
        required=True,
        max_length=100
    )
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "not_received", self.opener, {
            "Invoice id": str(self.invoice),
            "Payment method used": str(self.pay_method),
            "Payment date": str(self.pay_date),
        })

class ReplaceModal(discord.ui.Modal, title="Replace"):
    purchase_type = discord.ui.TextInput(
        label="Is this a store purchase or a replacement?",
        placeholder="Do you want to replace a new account or is it a replacement of an old one?",
        required=True,
        max_length=200
    )
    invoice = discord.ui.TextInput(
        label="Invoice ID or Order ID",
        placeholder="Invoice id or the replacement order id",
        required=True,
        max_length=100
    )
    issue = discord.ui.TextInput(
        label="Describe the issue",
        placeholder="Describe the problem you are having with your account",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
    )
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener = opener

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, "replace", self.opener, {
            "Purchase vs Replacement": str(self.purchase_type),
            "Invoice/Order ID": str(self.invoice),
            "Issue": str(self.issue),
        })

class SupportModal(discord.ui.Modal, title="Support"):
    help_text = discord.ui.TextInput(
        label="How can we help you?",
        placeholder="Briefly describe how we can help you",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=2000
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

    @discord.ui.button(label="Purchase", style=discord.ButtonStyle.blurple, emoji="🍔", custom_id="nuvix:purchases")
    async def btn_purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PurchasesModal(interaction.user))

    @discord.ui.button(label="Replace", style=discord.ButtonStyle.gray, emoji="🧾", custom_id="nuvix:replace")
    async def btn_replace(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplaceModal(interaction.user))

    @discord.ui.button(label="Report", style=discord.ButtonStyle.blurple, emoji="⚠️", custom_id="nuvix:notreceived")
    async def btn_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NotReceivedModal(interaction.user))

# ─────────────────────────────────────────────────────────────────────────────
# Ticket creation & message

async def create_ticket(
    interaction: discord.Interaction,
    kind: str,
    opener: discord.Member,
    fields: Dict[str, str]
):
    guild = interaction.guild
    assert guild is not None

    if opener.id in BLACKLIST:
        await interaction.response.send_message("You are blacklisted from creating tickets.", ephemeral=True)
        return

    # Category
    cat = await get_category(guild, kind)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True, attach_files=True),
    }
    # Staff roles
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=True, manage_messages=True
            )

    name_prefix = {
        "purchases": "purch-",
        "not_received": "nrcv-",
        "replace": "repl-",
        "support": "supp-",
    }.get(kind, "ticket-")
    channel_name = f"{name_prefix}{opener.name}".lower()

    ch = await guild.create_text_channel(
        name=channel_name,
        category=cat,
        overwrites=overwrites,
        reason=f"Ticket opened by {opener} ({kind})"
    )

    # Compose the opening embed
    title_map = {
        "purchases": "Purchases Ticket",
        "not_received": "Product not received",
        "replace": "Replace Ticket",
        "support": "Support Ticket",
    }
    e = make_embed(title_map.get(kind, "Support Ticket"))
    e.description = (
        "Please wait until one of our support team members can help you. "
        "**Response time may vary to many factors, so please be patient.**"
    )
    e.add_field(name="Assigned staff", value="*(none yet)*", inline=False)
    field_text = "\n".join(f"**{k}:** {v}" for k, v in fields.items())
    e.add_field(name="Form Details", value=field_text or "*No data*", inline=False)

    view = TicketControlsView(opener_id=opener.id)

    await ch.send(content=opener.mention, embed=e, view=view)

    await interaction.response.send_message(
        f"Ticket created: {ch.mention}", ephemeral=True
    )

    # Log creation
    await log_channel(bot, TICKETS_LOGS_CHANNEL_ID,
                      make_embed("Ticket Created",
                                 f"Type: **{kind}**\nUser: {opener.mention}\nChannel: {ch.mention}"))

class TicketControlsView(discord.ui.View):
    def __init__(self, opener_id: int):
        super().__init__(timeout=None)
        self.opener_id = opener_id

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="nuvix:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only staff can close
        if not is_staff(interaction.user):
            await interaction.response.send_message("Only staff can close tickets.", ephemeral=True)
            return
        await close_ticket(interaction)

    @discord.ui.button(label="Assign me", emoji="👋", style=discord.ButtonStyle.success, custom_id="nuvix:assign")
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("Only staff can assign.", ephemeral=True)
            return
        await assign_staff(interaction, interaction.user)

# ─────────────────────────────────────────────────────────────────────────────
# Transcript + Close + Review

async def render_transcript_html(channel: discord.TextChannel) -> bytes:
    messages = [m async for m in channel.history(limit=200, oldest_first=True)]
    rows = []
    for m in messages:
        ts = m.created_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = discord.utils.escape_markdown(m.author.display_name)
        content = discord.utils.escape_markdown(m.content or "")
        rows.append(f"<p><b>[{ts}] {author}:</b> {content}</p>")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Transcript - {channel.name}</title></head>
<body>
<h2>Transcript — {channel.guild.name} / #{channel.name}</h2>
{' '.join(rows) if rows else '<p><i>No messages</i></p>'}
</body></html>"""
    return html.encode("utf-8")

async def send_review_request(user: discord.User, ticket_channel: discord.TextChannel):
    try:
        dm = await user.create_dm()
        view = discord.ui.View(timeout=600)

        class StarsSelect(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(label="⭐", value="1"),
                    discord.SelectOption(label="⭐⭐", value="2"),
                    discord.SelectOption(label="⭐⭐⭐", value="3"),
                    discord.SelectOption(label="⭐⭐⭐⭐", value="4"),
                    discord.SelectOption(label="⭐⭐⭐⭐⭐", value="5"),
                ]
                super().__init__(placeholder="Rate your support (1–5 stars)", options=options, min_values=1, max_values=1, custom_id="nuvix:review:stars")

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.send_modal(ReviewModal(stars=self.values[0]))

        class ReviewModal(discord.ui.Modal, title="Leave a review"):
            extra = discord.ui.TextInput(
                label="Anything you want to add?",
                placeholder="Optional comment",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000
            )
            def __init__(self, stars: str):
                super().__init__(timeout=600)
                self.stars = stars

            async def on_submit(self, interaction: discord.Interaction):
                stars = int(self.stars)
                comment = str(self.extra).strip() if self.extra else ""
                # Send to reviews channel
                ch = bot.get_channel(REVIEWS_CHANNEL_ID)
                if isinstance(ch, discord.TextChannel):
                    emb = make_embed("New Ticket Review")
                    emb.add_field(name="Stars", value=f"{'⭐'*stars} ({stars}/5)", inline=False)
                    emb.add_field(name="User", value=f"{interaction.user.mention}", inline=True)
                    emb.add_field(name="Ticket", value=f"{ticket_channel.mention}", inline=True)
                    if comment:
                        emb.add_field(name="Comment", value=comment, inline=False)
                    await ch.send(embed=emb)
                await interaction.response.send_message("Thanks! Your review has been submitted.", ephemeral=True)

        view.add_item(StarsSelect())
        e = make_embed("How was your support?")
        e.description = "Please rate your ticket experience and add an optional comment."
        await dm.send(embed=e, view=view)
    except Exception:
        pass

async def close_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)

    # Gather opener (try from first message mention)
    opener: Optional[discord.Member] = None
    async for m in channel.history(limit=25, oldest_first=True):
        if m.mentions:
            opener = m.mentions[0]
            break

    # transcript
    data = await render_transcript_html(channel)
    file = discord.File(io.BytesIO(data), filename=f"{channel.name}-transcript.html")

    # send to transcripts channel
    tlog = bot.get_channel(TRANSCRIPTS_CHANNEL_ID)
    if isinstance(tlog, discord.TextChannel):
        await tlog.send(content=f"Transcript for {channel.mention}", file=file)

    # DM user with transcript + review form
    if opener:
        try:
            dm = await opener.create_dm()
            await dm.send(content=f"Ticket **#{channel.name}** has been closed. Here is your transcript:", file=file)
            await send_review_request(opener, channel)
        except Exception:
            pass

    # Log close
    await log_channel(bot, TICKETS_LOGS_CHANNEL_ID,
                      make_embed("Ticket Closed", f"Channel: {channel.mention}\nBy: {interaction.user.mention}"))

    await interaction.response.send_message("Closing ticket…", ephemeral=True)
    try:
        await channel.delete(reason=f"Closed by {interaction.user}")
    except discord.Forbidden:
        await interaction.followup.send("I couldn't delete the channel (missing permissions).", ephemeral=True)

async def assign_staff(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    # Update the first embed field "Assigned staff"
    first_msg = None
    async for m in channel.history(limit=50, oldest_first=True):
        if m.author == bot.user and m.embeds:
            first_msg = m
            break
    if first_msg and first_msg.embeds:
        e = first_msg.embeds[0]
        new = make_embed(e.title or "Support Ticket", e.description or "")
        for f in e.fields:
            if f.name.lower().startswith("assigned"):
                continue
            new.add_field(name=f.name, value=f.value, inline=f.inline)
        new.add_field(name="Assigned staff", value=f"{member.mention}", inline=False)
        await first_msg.edit(embed=new)
    await interaction.response.send_message(f"Assigned to {member.mention}.", ephemeral=True)

# ─────────────────────────────────────────────────────────────────────────────
# Slash commands

def staff_only():
    async def predicate(interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return False
        return is_staff(interaction.user)
    return app_commands.check(predicate)

def owner_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.id in {OWNER_ID, COOWNER_ID}
    return app_commands.check(predicate)

@bot.tree.command(name="ping", description="Check bot latency (Pong!)")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! `{round(bot.latency*1000)}ms`", ephemeral=True)

@bot.tree.command(name="panel", description="Post the Nuvix ticket panel")
@staff_only()
async def panel(interaction: discord.Interaction):
    e = make_embed("Nuvix Tickets — Ticket Panel",
                   "Select a ticket category\nChoose the option that best fits your request.")
    await interaction.response.send_message(embed=e, view=TicketPanelView())
    await log_channel(bot, LOGS_CMD_USE_CHANNEL_ID, make_embed("/panel used", f"By: {interaction.user.mention} in {interaction.channel.mention}"))

@bot.tree.command(name="assign", description="Assign the current ticket to a staff member")
@staff_only()
@app_commands.describe(member="Staff member to assign")
async def assign(interaction: discord.Interaction, member: discord.Member):
    await assign_staff(interaction, member)

@bot.tree.command(name="unassign", description="Remove assigned staff info from ticket header")
@staff_only()
async def unassign(interaction: discord.Interaction):
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    # Remove "Assigned staff" field
    first_msg = None
    async for m in channel.history(limit=50, oldest_first=True):
        if m.author == bot.user and m.embeds:
            first_msg = m
            break
    if first_msg and first_msg.embeds:
        e = first_msg.embeds[0]
        new = make_embed(e.title or "Support Ticket", e.description or "")
        for f in e.fields:
            if f.name.lower().startswith("assigned"):
                continue
            new.add_field(name=f.name, value=f.value, inline=f.inline)
        await first_msg.edit(embed=new)
    await interaction.response.send_message("Unassigned.", ephemeral=True)

@bot.tree.command(name="add", description="Add a user to this ticket")
@staff_only()
@app_commands.describe(user="User to add")
async def add_user(interaction: discord.Interaction, user: discord.Member):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    await ch.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"Added {user.mention}.", ephemeral=True)

@bot.tree.command(name="remove", description="Remove a user from this ticket")
@staff_only()
@app_commands.describe(user="User to remove")
async def remove_user(interaction: discord.Interaction, user: discord.Member):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    await ch.set_permissions(user, overwrite=None)
    await interaction.response.send_message(f"Removed {user.mention}.", ephemeral=True)

@bot.tree.command(name="close", description="Close a ticket (staff only)")
@staff_only()
async def close_cmd(interaction: discord.Interaction):
    await close_ticket(interaction)

@bot.tree.command(name="transcript", description="Generate a transcript (HTML)")
@staff_only()
async def transcript(interaction: discord.Interaction):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    data = await render_transcript_html(ch)
    file = discord.File(io.BytesIO(data), filename=f"{ch.name}-transcript.html")
    await interaction.response.send_message("Transcript generated.", ephemeral=True)
    await ch.send(file=file)

# Priority command — Choice (no autocomplete)
@bot.tree.command(name="ticket_priority", description="Set visual priority tag in channel topic")
@staff_only()
@app_commands.describe(level="Priority level")
@app_commands.choices(level=[
    app_commands.Choice(name="low", value="low"),
    app_commands.Choice(name="normal", value="normal"),
    app_commands.Choice(name="high", value="high"),
    app_commands.Choice(name="critical", value="critical"),
])
async def ticket_priority(interaction: discord.Interaction, level: app_commands.Choice[str]):
    ch = interaction.channel
    assert isinstance(ch, discord.TextChannel)
    topic = ch.topic or ""
    # remove existing tag
    for tag in ("[P:low]", "[P:normal]", "[P:high]", "[P:critical]"):
        topic = topic.replace(tag, "")
    topic = f"{topic} [P:{level.value}]".strip()
    await ch.edit(topic=topic)
    await interaction.response.send_message(f"Set priority **{level.value}**.", ephemeral=True)

# Blacklist
@bot.tree.command(name="blacklist", description="Manage ticket blacklist")
@staff_only()
@app_commands.describe(action="add/remove/list", user="User to affect (add/remove)")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="list", value="list"),
])
async def blacklist(interaction: discord.Interaction, action: app_commands.Choice[str], user: Optional[discord.Member] = None):
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

# Staff stats (simple placeholders you can expand later)
@bot.tree.command(name="staffstats_me", description="View your own support statistics")
@staff_only()
async def staffstats_me(interaction: discord.Interaction):
    await interaction.response.send_message("Tickets today: 0 • Tickets this month: 0 • Total: 0 (placeholder)", ephemeral=True)

@bot.tree.command(name="staffstats_user", description="View statistics for another staff member")
@staff_only()
@app_commands.describe(user="Staff member")
async def staffstats_user(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.mention} — Tickets today: 0 • Tickets this month: 0 • Total: 0 (placeholder)", ephemeral=True)

@bot.tree.command(name="staffstats_leaderboard", description="View staff support leaderboard")
@staff_only()
async def staffstats_leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message("Leaderboard coming soon (placeholder).", ephemeral=True)

@bot.tree.command(name="staffstats_monthclaims", description="Show staff with N claims this month")
@staff_only()
@app_commands.describe(count="Minimum claims")
async def staffstats_monthclaims(interaction: discord.Interaction, count: int = 5):
    await interaction.response.send_message(f"Staff with ≥{count} claims this month (placeholder).", ephemeral=True)

# Help
@bot.tree.command(name="help", description="Displays a list of all commands")
async def help_cmd(interaction: discord.Interaction):
    cmds = [
        "`/panel` — Post the ticket panel",
        "`/ping` — Latency",
        "`/assign [member]` • `/unassign`",
        "`/add [user]` • `/remove [user]`",
        "`/close` • `/transcript`",
        "`/blacklist add|remove|list [user]`",
        "`/ticket_priority [low|normal|high|critical]`",
        "`/staffstats_me` • `/staffstats_user [member]`",
        "`/staffstats_leaderboard` • `/staffstats_monthclaims [count]`",
        "`/sync` (owner only)",
    ]
    e = make_embed("Nuvix Tickets — Help", "\n".join(cmds))
    await interaction.response.send_message(embed=e, ephemeral=True)

# Owner-only sync
@bot.tree.command(name="sync", description="Sync slash commands (owner only)")
@owner_only()
async def sync(interaction: discord.Interaction):
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        await interaction.response.send_message(f"Synced {len(synced)} commands to guild {GUILD_ID}.", ephemeral=True)
    else:
        synced = await bot.tree.sync()
        await interaction.response.send_message(f"Globally synced {len(synced)} commands.", ephemeral=True)

# ─────────────────────────────────────────────────────────────────────────────
# Events

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} | {now_utc_str()}")
    await log_channel(bot, PRIVATE_BOT_LOGS_CHANNEL_ID,
                      make_embed(f"{BOT_NAME} online", f"— {now_utc_str()}"))

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    await log_channel(bot, LOGS_CMD_USE_CHANNEL_ID,
                      make_embed("Command used", f"`/{command.name}` by {interaction.user.mention} in {interaction.channel.mention}"))

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    # For prefix commands (not used, but keep safety)
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    print(tb)

# ─────────────────────────────────────────────────────────────────────────────
# Run
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ NUVIX_TICKETS_TOKEN/TOKEN env var is required.")
    if KEEPALIVE:
        Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
