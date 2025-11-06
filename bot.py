# ==============================
# Nuvix Tickets — Render Edition
# ==============================
# • No usa .env — todo se toma de variables de entorno Render.
# • Incluye shim de audioop (para Python 3.12/3.13 en Render).
# • Slash commands: /ping, /ticket open, /ticket close.
# • Logs y transcripts automáticos.
# • Permisos de staff opcionales mediante STAFF_ROLE_IDS.

# --- Parche audioop ---
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
import datetime as dt
import discord
from discord import app_commands
from discord.ext import commands

# --- Variables Render ---
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "0"))
TICKET_CATEGORY_ID = int(os.environ.get("TICKET_CATEGORY_ID", "0"))
LOGS_CMD_USE_CHANNEL_ID = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_CHANNEL_ID = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))
STAFF_ROLE_IDS = [
    int(r)
    for r in os.environ.get("STAFF_ROLE_IDS", "").split(",")
    if r.strip().isdigit()
]

# --- Cliente Discord ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
TREE = bot.tree
BOT_NAME = "Nuvix Tickets"


# --- Utilidades ---
def log_now() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


async def send_channel_safe(channel_id: int, **kwargs):
    """Enviar mensaje a canal sin romper si no existe."""
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return
    try:
        await channel.send(**kwargs)
    except Exception:
        pass


# --- Eventos ---
@bot.event
async def on_ready():
    """Sincroniza slash commands y anuncia online."""
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
    activity = discord.Activity(
        type=discord.ActivityType.watching, name="tickets • /ticket open"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f"{BOT_NAME} is online!")


# --- Construcción de permisos ---
async def build_ticket_overwrites(guild: discord.Guild, opener: discord.Member):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        ),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )
    for role in opener.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )
    return overwrites


async def make_transcript(channel: discord.TextChannel) -> discord.File:
    """Crea un transcript de texto del canal."""
    lines = []
    async for msg in channel.history(limit=2000, oldest_first=True):
        created = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content.replace("\n", "\\n")
        lines.append(f"[{created}] {author}: {content}")
        for a in msg.attachments:
            lines.append(f"    [attachment] {a.filename} -> {a.url}")
    text = "\n".join(lines) if lines else "No messages."
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.txt")


# --- Slash Commands ---
@TREE.command(name="ping", description="Check if the bot is alive.")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)}ms", ephemeral=True
    )
    await send_channel_safe(
        LOGS_CMD_USE_CHANNEL_ID,
        content=f"🧪 /ping by {interaction.user} ({interaction.user.id}) in {interaction.guild}",
    )


ticket_group = app_commands.Group(name="ticket", description="Ticket commands")


@ticket_group.command(name="open", description="Open a new ticket.")
async def ticket_open(interaction: discord.Interaction, subject: str):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    if guild is None:
        return await interaction.followup.send(
            "This command can only be used in a server.", ephemeral=True
        )

    category = guild.get_channel(TICKET_CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        return await interaction.followup.send(
            "Ticket category not configured or invalid.", ephemeral=True
        )

    overwrites = await build_ticket_overwrites(guild, interaction.user)
    channel_name = f"ticket-{interaction.user.name[:20]}"

    try:
        ch = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user} ({interaction.user.id})",
        )
    except Exception as e:
        return await interaction.followup.send(f"Error creating ticket: {e}")

    embed = discord.Embed(
        title="🎫 New Ticket",
        description=f"**Subject:** {subject}\n**Opened by:** {interaction.user.mention}",
        color=discord.Color.brand_red(),
    )
    embed.set_footer(text=f"{BOT_NAME} • Opened at {log_now()}")

    await ch.send(content=interaction.user.mention, embed=embed)
    await interaction.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)

    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🆕 Ticket {ch.mention} opened by {interaction.user} — Subject: {subject}",
    )


@ticket_group.command(name="close", description="Close the current ticket.")
async def ticket_close(interaction: discord.Interaction, reason: str = "No reason given"):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        return await interaction.followup.send(
            "Use this inside a ticket channel.", ephemeral=True
        )

    if TICKET_CATEGORY_ID and channel.category_id != TICKET_CATEGORY_ID:
        return await interaction.followup.send("This channel is not a ticket.", ephemeral=True)

    file = await make_transcript(channel)
    await send_channel_safe(
        TRANSCRIPTS_CHANNEL_ID,
        content=f"🧾 Transcript for {channel.mention} — closed by {interaction.user} ({interaction.user.id}) — Reason: {reason}",
        file=file,
    )

    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🔒 Ticket {channel.name} closed by {interaction.user} — Reason: {reason}",
    )

    # Find original user to DM
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
if not TOKEN:
    raise RuntimeError("NUVIX_TICKETS_TOKEN is not set.")
bot.run(TOKEN)
