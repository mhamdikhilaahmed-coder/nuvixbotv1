# ==============================
# Nuvix Tickets — Render Edition (Classic Blue)
# ==============================
# • No usa .env — todo se toma de variables de entorno (Render).
# • Incluye shim de audioop (para Python 3.12/3.13 en Render).
# • Slash commands: /ping, /panel, /ticket open, /ticket close.
# • Panel con botones (Purchases, Product not received, Replace, Support) y modals.
# • Logs y transcripts automáticos.
# • Permisos de staff opcionales mediante STAFF_ROLE_IDS.

# --- Parche audioop (evita import error en Python 3.12/3.13) ---
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

# --- Librerías ---
import os
import io
import random
import string
import datetime as dt
import discord
from discord import app_commands
from discord.ext import commands

# --- Variables de entorno (Render) ---
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")

GUILD_ID = int(os.environ.get("GUILD_ID", "0"))
TICKET_CATEGORY_ID = int(os.environ.get("TICKET_CATEGORY_ID", "0"))

LOGS_CMD_USE_CHANNEL_ID = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))

FOOTER_TEXT = os.environ.get("FOOTER_TEXT", "Nuvix Tickets")
STAFF_ROLE_IDS = [
    int(r) for r in os.environ.get("STAFF_ROLE_IDS", "").split(",") if r.strip().isdigit()
]

# --- Cliente Discord ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
TREE = bot.tree
BOT_NAME = "Nuvix Tickets"

BLUE = discord.Color.blurple()

# --- Utils ---
def log_now() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def rand_code(n=4):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def send_channel_safe(channel_id: int, **kwargs):
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

async def build_ticket_overwrites(guild: discord.Guild, opener: discord.Member):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, attach_files=True,
            embed_links=True, read_message_history=True
        ),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )
    for role in opener.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )
    return overwrites

async def make_transcript(channel: discord.TextChannel) -> discord.File:
    lines = []
    async for msg in channel.history(limit=2000, oldest_first=True):
        created = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author} ({msg.author.id})"
        content = (msg.content or "").replace("\n", "\\n")
        lines.append(f"[{created}] {author}: {content}")
        for a in msg.attachments:
            lines.append(f"    [attachment] {a.filename} -> {a.url}")
    text = "\\n".join(lines) if lines else "No messages."
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.txt")

async def open_ticket(interaction: discord.Interaction, subject: str, extra_desc: str = ""):
    guild = interaction.guild
    if guild is None:
        return await interaction.followup.send("Use this in a server.", ephemeral=True)

    category = guild.get_channel(TICKET_CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        return await interaction.followup.send("Ticket category not configured.", ephemeral=True)

    overwrites = await build_ticket_overwrites(guild, interaction.user)
    channel_name = f"ticket-{interaction.user.name[:16]}-{rand_code()}"
    try:
        ch = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user} ({interaction.user.id})"
        )
    except Exception as e:
        return await interaction.followup.send(f"Error creating ticket: {e}", ephemeral=True)

    desc = f"**Subject:** {discord.utils.escape_markdown(subject)}\\n**Opened by:** {interaction.user.mention}"
    if extra_desc:
        desc += f"\\n\\n{extra_desc}"

    embed = discord.Embed(title="🎫 New Ticket", description=desc, color=BLUE)
    embed.set_footer(text=f"{FOOTER_TEXT} • Opened at {log_now()}")
    await ch.send(content=interaction.user.mention, embed=embed)

    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🆕 Ticket {ch.mention} opened by {interaction.user} — Subject: {subject}"
    )
    await interaction.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)

# --- Modals (formularios) ---
class PurchasesModal(discord.ui.Modal, title="Purchases"):
    want = discord.ui.TextInput(label="What do you want buy?", placeholder="Describe what you want buy", required=True, max_length=300)
    amount = discord.ui.TextInput(label="Amount for buy?", placeholder="Enter the quantity of the product you want to", required=True, max_length=50)
    payment = discord.ui.TextInput(label="Payment Method?", placeholder="What payment method do you want to use?", required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        subject = "Purchase request"
        details = f"**What:** {self.want.value}\\n**Amount:** {self.amount.value}\\n**Payment:** {self.payment.value}"
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, subject, details)

class NotReceivedModal(discord.ui.Modal, title="Product not received"):
    invoice = discord.ui.TextInput(label="Invoice id", placeholder="Put your invoice id", required=True, max_length=100)
    method = discord.ui.TextInput(label="What payment method did you use?", placeholder="Describe payment method did you use", required=True, max_length=100)
    when = discord.ui.TextInput(label="When you did the payment?", placeholder="Put the date about the when did the payment", required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        subject = "Product not received"
        details = f"**Invoice:** {self.invoice.value}\\n**Payment method:** {self.method.value}\\n**Date:** {self.when.value}"
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, subject, details)

class ReplaceModal(discord.ui.Modal, title="Replace"):
    type_ = discord.ui.TextInput(label="Is this a store purchase or a replacement?", placeholder="Do you want to replace a new account or is it a replacement for previous one?", required=True, max_length=150)
    invoice = discord.ui.TextInput(label="Invoice ID or Order ID", placeholder="Invoice id or the replacement order id", required=True, max_length=100)
    issue = discord.ui.TextInput(label="Describe the issue", style=discord.TextStyle.paragraph, placeholder="Describe the problem you are having with your account", required=True, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        subject = "Replacement request"
        details = f"**Type:** {self.type_.value}\\n**Invoice/Order:** {self.invoice.value}\\n**Issue:** {self.issue.value}"
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, subject, details)

class SupportModal(discord.ui.Modal, title="Support"):
    help = discord.ui.TextInput(label="How can we help you?", style=discord.TextStyle.paragraph, placeholder="Briefly describe how we can help you", required=True, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        subject = "Support"
        details = f"**Message:** {self.help.value}"
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, subject, details)

# --- Panel con botones ---
class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Purchases", style=discord.ButtonStyle.primary, emoji="🛒", custom_id="nvx:purchase")
    async def purchases(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PurchasesModal())

    @discord.ui.button(label="Product not received", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="nvx:notreceived")
    async def not_received(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NotReceivedModal())

    @discord.ui.button(label="Replace", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="nvx:replace")
    async def replace(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplaceModal())

    @discord.ui.button(label="Support", style=discord.ButtonStyle.success, emoji="🆘", custom_id="nvx:support")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SupportModal())

# --- Eventos ---
@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            await TREE.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await TREE.sync()
    except Exception:
        pass
    await send_channel_safe(
        PRIVATE_BOT_LOGS_CHANNEL_ID,
        content=f"✅ **{BOT_NAME}** online — {log_now()}",
    )
    activity = discord.Activity(type=discord.ActivityType.watching, name="tickets • /panel")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f"{BOT_NAME} is online!")

# --- Slash Commands ---
@TREE.command(name="ping", description="Check if the bot is alive.")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)
    await send_channel_safe(
        LOGS_CMD_USE_CHANNEL_ID,
        content=f"🧪 /ping by {interaction.user} ({interaction.user.id}) in {interaction.guild}",
    )

@TREE.command(name="panel", description="Post the ticket panel in this channel (admin only).")
@app_commands.checks.has_permissions(administrator=True)
async def panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Nuvix Tickets",
        description="**Select a ticket category...**",
        color=BLUE
    )
    embed.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=embed, view=TicketPanel())
    await send_channel_safe(
        LOGS_CMD_USE_CHANNEL_ID,
        content=f"📌 Panel posted in {interaction.channel.mention} by {interaction.user}"
    )

@panel_cmd.error
async def panel_cmd_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need **Administrator** to use this.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except:
            pass

ticket_group = app_commands.Group(name="ticket", description="Ticket commands")

@ticket_group.command(name="open", description="Open a new ticket quickly.")
async def ticket_open(interaction: discord.Interaction, subject: str):
    await interaction.response.defer(ephemeral=True)
    await open_ticket(interaction, subject)

@ticket_group.command(name="close", description="Close the current ticket.")
async def ticket_close(interaction: discord.Interaction, reason: str = "No reason given"):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await interaction.followup.send("Use this inside a ticket channel.", ephemeral=True)
    if TICKET_CATEGORY_ID and channel.category_id != TICKET_CATEGORY_ID:
        return await interaction.followup.send("This channel is not a ticket.", ephemeral=True)

    file = await make_transcript(channel)
    await send_channel_safe(
        TRANSCRIPTS_CHANNEL_ID,
        content=(f"🧾 Transcript for {channel.mention} — closed by {interaction.user} "
                 f"({interaction.user.id}) — Reason: {reason}"),
        file=file,
    )
    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🔒 Ticket {channel.name} closed by {interaction.user} — Reason: {reason}",
    )

    opener = None
    async for m in channel.history(limit=50, oldest_first=True):
        if not m.author.bot:
            opener = m.author
            break
    if opener:
        try:
            embed = discord.Embed(
                title="🔒 Your Ticket was closed",
                description=f"**Reason:** {reason}",
                color=discord.Color.greyple(),
            )
            await opener.send(embed=embed)
        except Exception:
            pass

    try:
        await channel.delete(reason=f"Closed by {interaction.user} — {reason}")
    except Exception as e:
        return await interaction.followup.send(f"Failed to delete channel: {e}", ephemeral=True)
    await interaction.followup.send("Ticket closed.", ephemeral=True)

TREE.add_command(ticket_group)

# --- Arranque ---
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("NUVIX_TICKETS_TOKEN is not set.")
    bot.run(TOKEN)
