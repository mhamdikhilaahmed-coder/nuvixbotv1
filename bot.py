# (bot.py content generated as in previous step)
# ==============================
# Nuvix Tickets — Render Web Service Edition
# ==============================
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **kw: None, mul=lambda *a, **kw: None, bias=lambda *a, **kw: None,
        avg=lambda *a, **kw: 0, max=lambda *a, **kw: 0, minmax=lambda *a, **kw: (0, 0),
        rms=lambda *a, **kw: 0, cross=lambda *a, **kw: 0, reverse=lambda *a, **kw: b"",
        tostereo=lambda *a, **kw: b"", tomono=lambda *a, **kw: b"",
    )
import os, io, asyncio, datetime as dt, threading, html
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from keepalive import run as run_flask

BOT_DISPLAY_NAME = os.environ.get("BOT_DISPLAY_NAME", "Nuvix Tickets")
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "0"))
LOGS_CMD_USE_CHANNEL_ID = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))
STAFF_ROLE_IDS = [int(x) for x in os.environ.get("STAFF_ROLE_IDS", "").split(",") if x.strip().isdigit()]
OWNER_ROLE_IDS = [int(os.environ.get("OWNER_ID", "0"))] if os.environ.get("OWNER_ID") else []
COOWNER_ROLE_IDS = [int(os.environ.get("COOWNER_ID", "0"))] if os.environ.get("COOWNER_ID") else []
TICKET_CATEGORY_ID = int(os.environ.get("TICKET_CATEGORY_ID", "0"))
ICON_URL = os.environ.get("ICON_URL", "")
BANNER_URL = os.environ.get("BANNER_URL", "")
EMBED_COLOR = int(os.environ.get("EMBED_COLOR", "0x2f6fe4"), 16) if os.environ.get("EMBED_COLOR","").startswith("0x") else 0x2f6fe4
FOOTER_TEXT = os.environ.get("FOOTER_TEXT", "Nuvix Market • Your wishes, more cheap!")
CONNECTED_SINCE = dt.datetime.now(dt.timezone.utc).isoformat()
os.environ["CONNECTED_SINCE"] = CONNECTED_SINCE

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
BLUE = discord.Color(EMBED_COLOR)

def now_str():
    try:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

async def fetch_channel_safe(cid:int):
    if not cid: return None
    ch = bot.get_channel(cid)
    if ch: return ch
    try: return await bot.fetch_channel(cid)
    except Exception: return None

async def send_channel_safe(cid:int, **kwargs):
    ch = await fetch_channel_safe(cid)
    if not ch: return
    try: await ch.send(**kwargs)
    except Exception: pass

def staff_or_admin(member: discord.Member)->bool:
    if member.guild_permissions.administrator: return True
    if member.id in OWNER_ROLE_IDS or member.id in COOWNER_ROLE_IDS: return True
    return any(r.id in set(STAFF_ROLE_IDS) for r in member.roles)

def admin_plus(member: discord.Member)->bool:
    return member.guild_permissions.administrator or member.id in OWNER_ROLE_IDS or member.id in COOWNER_ROLE_IDS

async def build_overwrites(guild: discord.Guild, opener: discord.Member):
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    for role in opener.roles:
        if role.permissions.administrator:
            ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    return ow

async def make_transcript_html(channel: discord.TextChannel)->discord.File:
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>Transcript</title>",
             "<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0b1220;color:#e8eefb;padding:20px} .msg{margin:10px 0;padding:10px;border-radius:10px;background:#111a2e} .meta{opacity:.7;font-size:12px;margin-bottom:6px} .content{white-space:pre-wrap} .att a{color:#9ecbff}</style>",
             "</head><body>",
             f"<h2>Transcript — #{html.escape(channel.name)}</h2>",
             f"<div class='meta'>Channel ID: {channel.id} • Generated: {html.escape(now_str())}</div>"]
    async for m in channel.history(limit=3000, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        parts.append("<div class='msg'>")
        parts.append(f"<div class='meta'>{html.escape(str(m.author))} ({m.author.id}) • {ts}</div>")
        parts.append(f"<div class='content'>{html.escape(m.content or '')}</div>")
        if m.attachments:
            parts.append("<div class='att'>Attachments:<ul>")
            for a in m.attachments:
                parts.append(f"<li><a href='{html.escape(a.url)}' target='_blank'>{html.escape(a.filename)}</a></li>")
            parts.append("</ul></div>")
        parts.append("</div>")
    parts.append("</body></html>")
    data = "\n".join(parts).encode("utf-8")
    return discord.File(io.BytesIO(data), filename=f"transcript_{channel.id}.html")

async def dm_safe(user: discord.User, **kwargs):
    try: await user.send(**kwargs)
    except Exception: pass

class StarsView(discord.ui.View):
    def __init__(self, closer: discord.Member, channel_name:str):
        super().__init__(timeout=300)
        self.closer = closer
        self.channel_name = channel_name
    @discord.ui.button(label="★", style=discord.ButtonStyle.primary)
    async def s1(self, interaction: discord.Interaction, button: discord.ui.Button): await self._submit(interaction, 1)
    @discord.ui.button(label="★★", style=discord.ButtonStyle.primary)
    async def s2(self, interaction: discord.Interaction, button: discord.ui.Button): await self._submit(interaction, 2)
    @discord.ui.button(label="★★★", style=discord.ButtonStyle.primary)
    async def s3(self, interaction: discord.Interaction, button: discord.ui.Button): await self._submit(interaction, 3)
    @discord.ui.button(label="★★★★", style=discord.ButtonStyle.primary)
    async def s4(self, interaction: discord.Interaction, button: discord.ui.Button): await self._submit(interaction, 4)
    @discord.ui.button(label="★★★★★", style=discord.ButtonStyle.success)
    async def s5(self, interaction: discord.Interaction, button: discord.ui.Button): await self._submit(interaction, 5)
    async def _submit(self, interaction: discord.Interaction, stars:int):
        modal = ReviewModal(stars, self.closer, self.channel_name); await interaction.response.send_modal(modal)

class ReviewModal(discord.ui.Modal, title="Rate your support ✨"):
    comment = discord.ui.TextInput(label="Additional comments (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    def __init__(self, stars:int, closer: discord.Member, channel_name:str):
        super().__init__(); self.stars=stars; self.closer=closer; self.channel_name=channel_name
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Thanks for your feedback!", ephemeral=True)
        stars_text = "★"*self.stars + "☆"*(5-self.stars)
        embed = discord.Embed(title="New Ticket Review",
            description=f"**Channel:** `{self.channel_name}`\n**User:** {interaction.user.mention} ({interaction.user.id})\n**Closer:** {self.closer.mention} ({self.closer.id})\n**Stars:** {stars_text}\n**Comment:** {self.comment.value or '—'}",
            color=BLUE)
        if ICON_URL: embed.set_thumbnail(url=ICON_URL)
        embed.set_footer(text=FOOTER_TEXT)
        await send_channel_safe(REVIEWS_CHANNEL_ID, embed=embed)

class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        opts=[
            discord.SelectOption(label="Purchases", value="purchases", emoji="🧾", description="Order and billing issues"),
            discord.SelectOption(label="Product not received", value="not_received", emoji="📦", description="Tracking or delivery delays"),
            discord.SelectOption(label="Replace", value="replace", emoji="🔁", description="Defective or wrong item"),
            discord.SelectOption(label="Support", value="support", emoji="🛠️", description="General help and questions"),
        ]
        super().__init__(placeholder="Select a ticket category", min_values=1, max_values=1, options=opts)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal(self.values[0]))

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketCategorySelect())

class TicketModal(discord.ui.Modal, title="Create your ticket"):
    def __init__(self, category_key:str):
        self.category_key=category_key; super().__init__(timeout=None)
        if category_key=="purchases":
            self.order_id=discord.ui.TextInput(label="Order ID", required=True, max_length=64)
            self.product=discord.ui.TextInput(label="Product", required=True, max_length=128)
            self.payment=discord.ui.TextInput(label="Payment method", required=True, max_length=64)
            self.issue=discord.ui.TextInput(label="Describe the issue", style=discord.TextStyle.paragraph, required=True, max_length=1000)
            for x in (self.order_id,self.product,self.payment,self.issue): self.add_item(x)
        elif category_key=="not_received":
            self.order_id=discord.ui.TextInput(label="Order ID", required=True, max_length=64)
            self.expected=discord.ui.TextInput(label="Expected date (YYYY-MM-DD)", required=False, max_length=32)
            self.tracking=discord.ui.TextInput(label="Tracking Number (optional)", required=False, max_length=64)
            self.issue=discord.ui.TextInput(label="Extra details", style=discord.TextStyle.paragraph, required=False, max_length=1000)
            for x in (self.order_id,self.expected,self.tracking,self.issue): self.add_item(x)
        elif category_key=="replace":
            self.order_id=discord.ui.TextInput(label="Order ID", required=True, max_length=64)
            self.product=discord.ui.TextInput(label="Product", required=True, max_length=128)
            self.reason=discord.ui.TextInput(label="Reason for replacement", style=discord.TextStyle.paragraph, required=True, max_length=1000)
            self.proof=discord.ui.TextInput(label="Proof link (image/video)", required=False, max_length=300)
            for x in (self.order_id,self.product,self.reason,self.proof): self.add_item(x)
        else:
            self.topic=discord.ui.TextInput(label="Topic", required=True, max_length=100)
            self.details=discord.ui.TextInput(label="Describe your issue", style=discord.TextStyle.paragraph, required=True, max_length=1000)
            for x in (self.topic,self.details): self.add_item(x)
    async def on_submit(self, interaction: discord.Interaction):
        guild=interaction.guild
        if not guild: return await interaction.response.send_message("Use this inside the server.", ephemeral=True)
        category=guild.get_channel(TICKET_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message("Ticket category is not configured.", ephemeral=True)
        ow=await build_overwrites(guild, interaction.user)
        base={"purchases":"purch","not_received":"nrecv","replace":"repl","support":"supp"}[self.category_key]
        name=f"{base}-{interaction.user.name[:18]}".lower()
        try: ch=await guild.create_text_channel(name=name, category=category, overwrites=ow, reason=f"Ticket by {interaction.user} ({interaction.user.id})")
        except Exception as e: return await interaction.response.send_message(f"Failed creating channel: {e}", ephemeral=True)
        if self.category_key=="purchases":
            desc=f"**Category:** Purchases\n**Order ID:** `{self.order_id.value}`\n**Product:** {self.product.value}\n**Payment:** {self.payment.value}\n**Issue:** {self.issue.value}"
        elif self.category_key=="not_received":
            desc=f"**Category:** Product not received\n**Order ID:** `{self.order_id.value}`\n**Expected:** {self.expected.value or '—'}\n**Tracking:** {self.tracking.value or '—'}\n**Details:** {self.issue.value or '—'}"
        elif self.category_key=="replace":
            desc=f"**Category:** Replace\n**Order ID:** `{self.order_id.value}`\n**Product:** {self.product.value}\n**Reason:** {self.reason.value}\n**Proof:** {self.proof.value or '—'}"
        else:
            desc=f"**Category:** Support\n**Topic:** {self.topic.value}\n**Details:** {self.details.value}"
        emb=discord.Embed(title="🎫 New Ticket", description=desc, color=BLUE)
        if ICON_URL: emb.set_thumbnail(url=ICON_URL)
        if BANNER_URL: emb.set_image(url=BANNER_URL)
        emb.set_footer(text=f"{FOOTER_TEXT} • Opened {now_str()}")
        mention_staff=""
        if STAFF_ROLE_IDS:
            roles=[guild.get_role(r) for r in STAFF_ROLE_IDS]; roles=[r for r in roles if r]
            if roles: mention_staff=" ".join(r.mention for r in roles)
        await ch.send(content=f"{interaction.user.mention} {mention_staff}".strip(), embed=emb)
        await interaction.response.send_message(f"Ticket created: {ch.mention}", ephemeral=True)
        await send_channel_safe(TICKETS_LOGS_CHANNEL_ID, content=f"🆕 **Ticket opened** {ch.mention} by {interaction.user} ({interaction.user.id}) — `{self.category_key}`")

@bot.event
async def on_ready():
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else: await tree.sync()
        await send_channel_safe(PRIVATE_BOT_LOGS_CHANNEL_ID, content=f"✅ **{BOT_DISPLAY_NAME}** online — commands synced at {now_str()}")
    except Exception as e:
        await send_channel_safe(PRIVATE_BOT_LOGS_CHANNEL_ID, content=f"⚠️ Online with sync error: {e}")
    act=discord.Activity(type=discord.ActivityType.watching, name="tickets • /panel")
    await bot.change_presence(status=discord.Status.online, activity=act)
    print(f"{BOT_DISPLAY_NAME} is online and commands synced.")

@tree.command(name="ping", description="Check if the bot is alive.")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)
    await send_channel_safe(LOGS_CMD_USE_CHANNEL_ID, content=f"🧪 /ping by {interaction.user} in {interaction.guild} at {now_str()}")

@tree.command(name="panel", description="Post the ticket panel in this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def panel_cmd(interaction: discord.Interaction, title: Optional[str]="Nuvix Tickets", subtitle: Optional[str]="Select a ticket category"):
    await interaction.response.defer(ephemeral=True)
    emb=discord.Embed(title=title or "Nuvix Tickets", description=subtitle or "Select a ticket category", color=BLUE)
    if ICON_URL: emb.set_thumbnail(url=ICON_URL)
    if BANNER_URL: emb.set_image(url=BANNER_URL)
    emb.set_footer(text=FOOTER_TEXT)
    await interaction.channel.send(embed=emb, view=TicketPanelView())
    await interaction.followup.send("Panel posted.", ephemeral=True)

@tree.command(name="sync", description="Force sync application commands.")
@app_commands.checks.has_permissions(administrator=True)
async def sync_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if GUILD_ID: await tree.sync(guild=discord.Object(id=GUILD_ID))
        else: await tree.sync()
        await interaction.followup.send("Commands synced ✅", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Sync failed: {e}", ephemeral=True)

def is_ticket_channel(ch: discord.TextChannel)->bool:
    return bool(TICKET_CATEGORY_ID and ch.category_id == TICKET_CATEGORY_ID)

@tree.command(name="ticket_close", description="Close the current ticket and send transcript & review.")
async def ticket_close(interaction: discord.Interaction, reason: Optional[str]="No reason provided"):
    await interaction.response.defer(ephemeral=True)
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.followup.send("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.followup.send("You need Staff+ to close tickets.", ephemeral=True)
    channel=interaction.channel
    html_file=await make_transcript_html(channel)
    await send_channel_safe(TRANSCRIPTS_CHANNEL_ID, content=f"🧾 Transcript for {channel.mention} — closed by {interaction.user.mention} • Reason: {reason}", file=html_file)
    opener=None
    async for m in channel.history(limit=100, oldest_first=True):
        if not m.author.bot: opener=m.author; break
    if opener:
        emb=discord.Embed(title="🔒 Your ticket was closed", description=f"**Reason:** {reason}", color=BLUE); emb.set_footer(text=FOOTER_TEXT)
        await dm_safe(opener, embed=emb); await dm_safe(opener, content="Here is your HTML transcript:", file=html_file)
        await dm_safe(opener, content="Please rate your support:", view=StarsView(interaction.user, channel.name))
    await send_channel_safe(TICKETS_LOGS_CHANNEL_ID, content=f"🔒 **Ticket closed** `{channel.name}` by {interaction.user.mention} • Reason: {reason}")
    try: await channel.delete(reason=f"Closed by {interaction.user} • {reason}")
    except Exception as e: return await interaction.followup.send(f"Failed to delete channel: {e}", ephemeral=True)
    await interaction.followup.send("Ticket closed ✅", ephemeral=True)

@tree.command(name="ticket_claim", description="Claim the current ticket.")
async def ticket_claim(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+ to claim tickets.", ephemeral=True)
    await interaction.response.send_message(f"Ticket claimed by {interaction.user.mention}", ephemeral=False)

@tree.command(name="ticket_unclaim", description="Unclaim the current ticket.")
async def ticket_unclaim(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+ to unclaim tickets.", ephemeral=True)
    await interaction.response.send_message("Ticket unclaimed.", ephemeral=False)

@tree.command(name="ticket_add", description="Add a user to this ticket.")
async def ticket_add(interaction: discord.Interaction, user: discord.Member):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    try:
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"Added {user.mention} to this ticket.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

@tree.command(name="ticket_remove", description="Remove a user from this ticket.")
async def ticket_remove(interaction: discord.Interaction, user: discord.Member):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    try:
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"Removed {user.mention} from this ticket.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

@tree.command(name="ticket_rename", description="Rename this ticket.")
async def ticket_rename(interaction: discord.Interaction, new_name:str):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    try:
        await interaction.channel.edit(name=new_name[:90])
        await interaction.response.send_message(f"Renamed to `{new_name}`.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

@tree.command(name="ticket_priority", description="Mark ticket priority.")
async def ticket_priority(interaction: discord.Interaction, level: app_commands.Choice[str]):
    await interaction.response.send_message(f"Priority set: {level.name}", ephemeral=False)

@ticket_priority.autocomplete("level")
async def ticket_priority_ac(interaction: discord.Interaction, current: str):
    choices=[app_commands.Choice(name="Low", value="low"), app_commands.Choice(name="Medium", value="med"), app_commands.Choice(name="High", value="high"), app_commands.Choice(name="Critical", value="crit")]
    return [c for c in choices if current.lower() in c.name.lower()][:25]

@tree.command(name="ticket_note", description="Add an internal note (visible to staff only).")
async def ticket_note(interaction: discord.Interaction, note:str):
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    await send_channel_safe(TICKETS_LOGS_CHANNEL_ID, content=f"📝 Note by {interaction.user.mention} in {interaction.channel.mention if hasattr(interaction.channel,'mention') else '#'}: {note}")
    await interaction.response.send_message("Noted.", ephemeral=True)

@tree.command(name="help", description="Show basic help.")
async def help_cmd(interaction: discord.Interaction):
    emb=discord.Embed(title="Nuvix Tickets — Help", description="Use `/panel` to post the panel. Open a ticket via the selector. Staff can manage tickets with `/ticket_*` commands.", color=BLUE)
    emb.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@tree.command(name="stats", description="Show basic stats.")
async def stats_cmd(interaction: discord.Interaction):
    emb=discord.Embed(title="Stats", description=f"Connected since: {CONNECTED_SINCE}", color=BLUE)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@tree.command(name="blacklist", description="Blacklist a user from opening tickets (stub).")
@app_commands.checks.has_permissions(administrator=True)
async def blacklist_cmd(interaction: discord.Interaction, user: discord.Member, reason: Optional[str]=""):
    await interaction.response.send_message(f"{user.mention} blacklisted (not persisted).", ephemeral=True)

@tree.command(name="unblacklist", description="Remove user from blacklist (stub).")
@app_commands.checks.has_permissions(administrator=True)
async def unblacklist_cmd(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{user.mention} removed from blacklist (not persisted).", ephemeral=True)

@tree.command(name="warn", description="Warn a user inside a ticket (stub).")
async def warn_cmd(interaction: discord.Interaction, user: discord.Member, reason: Optional[str]=""):
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    await interaction.response.send_message(f"{user.mention} warned. Reason: {reason}", ephemeral=False)

@tree.command(name="unwarn", description="Remove a warning (stub).")
async def unwarn_cmd(interaction: discord.Interaction, user: discord.Member):
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    await interaction.response.send_message(f"{user.mention} warning removed.", ephemeral=False)

@tree.command(name="ticket_lock", description="Lock the ticket (members cannot type).")
async def ticket_lock(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message("Ticket locked.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

@tree.command(name="ticket_unlock", description="Unlock the ticket.")
async def ticket_unlock(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
        await interaction.response.send_message("Ticket unlocked.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

@tree.command(name="transcript", description="Generate and send the HTML transcript now.")
async def transcript_cmd(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    html_file=await make_transcript_html(interaction.channel)
    await send_channel_safe(TRANSCRIPTS_CHANNEL_ID, content=f"🧾 Transcript generated by {interaction.user.mention} for {interaction.channel.mention}", file=html_file)
    await interaction.followup.send("Transcript generated & sent.", ephemeral=True)

@tree.command(name="delete", description="Delete this ticket immediately (Admin+ only).")
async def delete_cmd(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not admin_plus(interaction.user):
        return await interaction.response.send_message("You don’t have permission.", ephemeral=True)
    await interaction.channel.delete(reason=f"Deleted by {interaction.user}")

@tree.command(name="ticket_move", description="Move this ticket to another category (stub).")
async def ticket_move(interaction: discord.Interaction):
    await interaction.response.send_message("Move not implemented.", ephemeral=True)

@tree.command(name="addrole", description="Add a role to Staff list (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def addrole_cmd(interaction: discord.Interaction, role: discord.Role):
    STAFF_ROLE_IDS.append(role.id)
    await interaction.response.send_message(f"Added {role.mention} to Staff list (not persisted).", ephemeral=True)

@tree.command(name="removerole", description="Remove a role from Staff list (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def removerole_cmd(interaction: discord.Interaction, role: discord.Role):
    try:
        STAFF_ROLE_IDS.remove(role.id)
        await interaction.response.send_message(f"Removed {role.mention} from Staff list (runtime).", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("Role not found in list.", ephemeral=True)

@tree.command(name="setcategory", description="Set ticket category ID (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def setcategory_cmd(interaction: discord.Interaction, category: discord.CategoryChannel):
    global TICKET_CATEGORY_ID; TICKET_CATEGORY_ID = category.id
    await interaction.response.send_message(f"Ticket category set to `{category.name}` ({category.id})", ephemeral=True)

@tree.command(name="setlogs", description="Set ticket logs channel (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def setlogs_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    global TICKETS_LOGS_CHANNEL_ID; TICKETS_LOGS_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"Ticket logs set to {channel.mention}", ephemeral=True)

@tree.command(name="setreview", description="Set reviews channel (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def setreview_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    global REVIEWS_CHANNEL_ID; REVIEWS_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"Reviews channel set to {channel.mention}", ephemeral=True)

@tree.command(name="settranscripts", description="Set transcripts channel (runtime only).")
@app_commands.checks.has_permissions(administrator=True)
async def settranscripts_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    global TRANSCRIPTS_CHANNEL_ID; TRANSCRIPTS_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"Transcripts channel set to {channel.mention}", ephemeral=True)

@tree.command(name="assign", description="Assign this ticket to a staff member.")
async def assign_cmd(interaction: discord.Interaction, staff: discord.Member):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Trial Support or higher.", ephemeral=True)
    await interaction.response.send_message(f"Ticket assigned to {staff.mention}.", ephemeral=False)

@tree.command(name="unassign", description="Remove assignment.")
async def unassign_cmd(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Trial Support or higher.", ephemeral=True)
    await interaction.response.send_message("Ticket unassigned.", ephemeral=False)

@tree.command(name="note_dm", description="Send a DM note to the ticket opener (tries to detect).")
async def note_dm_cmd(interaction: discord.Interaction, message:str):
    if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("Use this inside a ticket channel.", ephemeral=True)
    if not staff_or_admin(interaction.user):
        return await interaction.response.send_message("You need Staff+.", ephemeral=True)
    opener=None
    async for m in interaction.channel.history(limit=100, oldest_first=True):
        if not m.author.bot: opener=m.author; break
    if opener:
        await dm_safe(opener, content=f"Staff note: {message}")
        await interaction.response.send_message("Note sent via DM.", ephemeral=True)
    else:
        await interaction.response.send_message("Could not detect the opener.", ephemeral=True)

@tree.command(name="about", description="About this bot.")
async def about_cmd(interaction: discord.Interaction):
    emb=discord.Embed(title="Nuvix Tickets", description="Ticket management with panel, transcripts and reviews.", color=BLUE)
    if ICON_URL: emb.set_thumbnail(url=ICON_URL)
    if BANNER_URL: emb.set_image(url=BANNER_URL)
    emb.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=emb, ephemeral=True)

def start_flask():
    run_flask()

def main():
    if not TOKEN: raise RuntimeError("NUVIX_TICKETS_TOKEN is not set.")
    t = threading.Thread(target=start_flask, daemon=True); t.start()
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
