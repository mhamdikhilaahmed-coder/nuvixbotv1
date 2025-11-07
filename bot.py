# ==============================
# Nuvix Tickets — Nebula Clone
# ==============================
# • English UI. Blue classic embeds.
# • Panel identical to Nebula (icon, banner, 4 options).
# • Each ticket type creates its channel in its OWN category:
#   - SUPPORT_CATEGORY_ID
#   - PURCHASES_CATEGORY_ID
#   - NOT_RECEIVED_CATEGORY_ID
#   - REPLACE_CATEGORY_ID
# • DM review (1–5 stars) on close, logs & transcripts.
# • Flask keep-alive endpoint for Render web service.

# --- audioop shim for Python 3.12+ on Render (discord.py imports it indirectly) ---
import sys, types
if "audioop" not in sys.modules:
    sys.modules["audioop"] = types.SimpleNamespace(
        add=lambda *a, **kw: None, mul=lambda *a, **kw: None, bias=lambda *a, **kw: None,
        avg=lambda *a, **kw: 0, max=lambda *a, **kw: 0, minmax=lambda *a, **kw: (0, 0),
        rms=lambda *a, **kw: 0, cross=lambda *a, **kw: 0, reverse=lambda *a, **kw: b"",
        tostereo=lambda *a, **kw: b"", tomono=lambda *a, **kw: b"",
    )

# --- std libs ---
import os, io
from datetime import datetime, timezone

# --- third-party ---
import discord
from discord import app_commands
from discord.ext import commands, tasks

# --- optional keep-alive (Flask) ---
try:
    from keep_alive import keep_alive
except Exception:
    def keep_alive(): pass

# -----------------------------
# ENV
# -----------------------------
TOKEN = os.environ.get("NUVIX_TICKETS_TOKEN")

GUILD_ID = int(os.environ.get("GUILD_ID", "0"))

# Per-type ticket categories (REQUIRED so tickets are classified)
SUPPORT_CATEGORY_ID        = int(os.environ.get("SUPPORT_CATEGORY_ID", "0"))
PURCHASES_CATEGORY_ID      = int(os.environ.get("PURCHASES_CATEGORY_ID", "0"))
NOT_RECEIVED_CATEGORY_ID   = int(os.environ.get("NOT_RECEIVED_CATEGORY_ID", "0"))
REPLACE_CATEGORY_ID        = int(os.environ.get("REPLACE_CATEGORY_ID", "0"))

# Logs / transcripts / reviews
LOGS_CMD_USE_CHANNEL_ID      = int(os.environ.get("LOGS_CMD_USE_CHANNEL_ID", "0"))
TICKETS_LOGS_CHANNEL_ID      = int(os.environ.get("TICKETS_LOGS_CHANNEL_ID", "0"))
PRIVATE_BOT_LOGS_CHANNEL_ID  = int(os.environ.get("PRIVATE_BOT_LOGS_CHANNEL_ID", "0"))
TRANSCRIPTS_CHANNEL_ID       = int(os.environ.get("TRANSCRIPTS_CHANNEL_ID", "0"))
REVIEWS_CHANNEL_ID           = int(os.environ.get("REVIEWS_CHANNEL_ID", "0"))

# Staff roles (comma separated ids)
STAFF_ROLE_IDS = [int(x) for x in os.environ.get("STAFF_ROLE_IDS", "").split(",") if x.strip().isdigit()]

# Brand / visuals
BOT_NAME   = os.environ.get("BRAND_NAME", "Nuvix Tickets")
BANNER_URL = os.environ.get("BANNER_URL", "")
ICON_URL   = os.environ.get("ICON_URL", "")
FOOTER_TXT = os.environ.get("FOOTER_TEXT", "Nuvix Tickets • Your wishes, more cheap!")

# Owner / Co-owner (for future admin checks if needed)
OWNER_ID    = int(os.environ.get("OWNER_ID", "0"))
COOWNER_ID  = int(os.environ.get("COOWNER_ID", "0"))

BLUE = discord.Color.blurple()

# -----------------------------
# Discord client
# -----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def send_channel_safe(channel_id: int, **kwargs):
    if not channel_id:
        return
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    try:
        await channel.send(**kwargs)
    except Exception:
        pass


@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            await tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await tree.sync()
    except Exception:
        pass

    await send_channel_safe(
        PRIVATE_BOT_LOGS_CHANNEL_ID,
        embed=discord.Embed(
            title=f"✅ {BOT_NAME} online",
            description=now_utc_str(),
            color=BLUE,
        )
    )
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="tickets • /panel")
    )
    print(f"{BOT_NAME} is online.")


# -----------------------------
# Permissions
# -----------------------------
def staff_overwrite():
    return discord.PermissionOverwrite(
        view_channel=True, send_messages=True, read_message_history=True, manage_messages=True
    )

async def build_overwrites(guild: discord.Guild, opener: discord.Member):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        opener: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                            attach_files=True, embed_links=True,
                                            read_message_history=True),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = staff_overwrite()

    # Allow server admins too
    for role in opener.roles:
        if role.permissions.administrator:
            overwrites[role] = staff_overwrite()
    return overwrites


async def make_transcript(channel: discord.TextChannel) -> discord.File:
    lines = []
    async for msg in channel.history(limit=2000, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        content = (msg.content or "").replace("\n", "\\n")
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content}")
        for a in msg.attachments:
            lines.append(f"    [attachment] {a.filename} -> {a.url}")
    text = "\n".join(lines) if lines else "No messages."
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.txt")


# -----------------------------
# Panel + Select + Modals
# -----------------------------
class TicketKind(discord.Enum):
    SUPPORT = "support"
    PURCHASE = "purchase"
    NOT_RECEIVED = "not_received"
    REPLACE = "replace"


def panel_embed() -> discord.Embed:
    e = discord.Embed(
        title=f"{BOT_NAME} — Ticket Panel",
        description="**Select a ticket category**\nChoose the option that best fits your request.",
        color=BLUE
    )
    if ICON_URL:
        e.set_author(name=BOT_NAME, icon_url=ICON_URL)
    if BANNER_URL:
        e.set_image(url=BANNER_URL)
    e.set_footer(text=FOOTER_TXT)
    return e


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Purchases", description="To purchase products", emoji="🛒", value=TicketKind.PURCHASE.value),
            discord.SelectOption(label="Product not received", description="Support for products not received", emoji="🚫", value=TicketKind.NOT_RECEIVED.value),
            discord.SelectOption(label="Replace", description="Request product replacement", emoji="🧾", value=TicketKind.REPLACE.value),
            discord.SelectOption(label="Support", description="Receive support from the staff team", emoji="🆘", value=TicketKind.SUPPORT.value),
        ]
        super().__init__(placeholder="Select a ticket category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == TicketKind.PURCHASE.value:
            await interaction.response.send_modal(PurchaseModal())
        elif value == TicketKind.NOT_RECEIVED.value:
            await interaction.response.send_modal(NotReceivedModal())
        elif value == TicketKind.REPLACE.value:
            await interaction.response.send_modal(ReplaceModal())
        else:
            await interaction.response.send_modal(SupportModal())


class PanelView(discord.ui.View):
    def __init__(self, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.add_item(TicketSelect())


# ----- Modals (forms) -----
class PurchaseModal(discord.ui.Modal, title="Purcharses"):
    what = discord.ui.TextInput(label="What do you want buy?", placeholder="Describe what you want buy", required=True, max_length=300)
    amount = discord.ui.TextInput(label="Amount for buy?", placeholder="Enter the quantity of the product you want to", required=True, max_length=100)
    method = discord.ui.TextInput(label="Payment Method?", placeholder="What payment method do you want to use?", required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, TicketKind.PURCHASE, {
            "What do you want buy?": str(self.what),
            "Amount for buy?": str(self.amount),
            "Payment Method?": str(self.method),
        })


class NotReceivedModal(discord.ui.Modal, title="Product not received"):
    invoice = discord.ui.TextInput(label="Invoice id", placeholder="Put your invoice id", required=True, max_length=100)
    method = discord.ui.TextInput(label="What payment method did you use?", placeholder="Describe payment method did you use", required=True, max_length=100)
    when   = discord.ui.TextInput(label="When you did the payment?", placeholder="Put the date about the when did the payment", required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, TicketKind.NOT_RECEIVED, {
            "Invoice id": str(self.invoice),
            "Payment method used": str(self.method),
            "Payment date": str(self.when),
        })


class ReplaceModal(discord.ui.Modal, title="Replace"):
    store_or_repl = discord.ui.TextInput(label="Is this a store purchase or a replacement?", placeholder="Do you want to replace a new account or is it a replacement for an existing one?", required=True, max_length=200)
    invoice = discord.ui.TextInput(label="Invoice ID or Order ID", placeholder="Invoice id or the replacement order id", required=True, max_length=100)
    desc    = discord.ui.TextInput(label="Describe the issue", placeholder="Describe the problem you are having with your account", required=True, style=discord.TextStyle.paragraph, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, TicketKind.REPLACE, {
            "Purchase or replacement?": str(self.store_or_repl),
            "Invoice / Order ID": str(self.invoice),
            "Issue": str(self.desc),
        })


class SupportModal(discord.ui.Modal, title="Support"):
    desc = discord.ui.TextInput(label="How can we help you?", placeholder="Briefly describe how we can help you", required=True, style=discord.TextStyle.paragraph, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, TicketKind.SUPPORT, {
            "Request": str(self.desc),
        })


# -----------------------------
# Ticket creation
# -----------------------------
async def category_for(kind: TicketKind, guild: discord.Guild) -> discord.CategoryChannel | None:
    mapping = {
        TicketKind.SUPPORT:        SUPPORT_CATEGORY_ID,
        TicketKind.PURCHASE:       PURCHASES_CATEGORY_ID,
        TicketKind.NOT_RECEIVED:   NOT_RECEIVED_CATEGORY_ID,
        TicketKind.REPLACE:        REPLACE_CATEGORY_ID,
    }
    cid = mapping.get(kind)
    if not cid:
        return None
    ch = guild.get_channel(cid)
    return ch if isinstance(ch, discord.CategoryChannel) else None


async def create_ticket(inter: discord.Interaction, kind: TicketKind, fields: dict):
    await inter.response.defer(ephemeral=True)

    guild = inter.guild
    if not guild:
        return await inter.followup.send("Use this inside a server.", ephemeral=True)

    category = await category_for(kind, guild)
    if category is None:
        return await inter.followup.send("Ticket category not configured.", ephemeral=True)

    overwrites = await build_overwrites(guild, inter.user)
    base = {
        TicketKind.SUPPORT: "support",
        TicketKind.PURCHASE: "purchase",
        TicketKind.NOT_RECEIVED: "notreceived",
        TicketKind.REPLACE: "replace",
    }[kind]
    name = f"{base}-{inter.user.name[:18]}"

    try:
        ch = await guild.create_text_channel(
            name=name, category=category, overwrites=overwrites,
            reason=f"{kind.value} ticket opened by {inter.user} ({inter.user.id})"
        )
    except Exception as e:
        return await inter.followup.send(f"Error creating ticket: {e}", ephemeral=True)

    embed = discord.Embed(
        title="🎫 New Ticket",
        description=f"**Opened by:** {inter.user.mention}",
        color=BLUE
    )
    for k, v in fields.items():
        embed.add_field(name=k, value=v or "—", inline=False)
    embed.set_footer(text=f"{FOOTER_TXT}")

    if ICON_URL:
        embed.set_author(name=f"{BOT_NAME}", icon_url=ICON_URL)

    await ch.send(content=inter.user.mention, embed=embed)
    await inter.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)

    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🆕 **{kind.name}** ticket {ch.mention} opened by {inter.user} ({inter.user.id})"
    )


# -----------------------------
# Review on close (stars)
# -----------------------------
class StarsView(discord.ui.View):
    def __init__(self, channel_name: str):
        super().__init__(timeout=60*60)
        self.channel_name = channel_name

    @discord.ui.button(label="★", style=discord.ButtonStyle.secondary)
    async def s1(self, _, interaction): await self.save(interaction, 1)
    @discord.ui.button(label="★★", style=discord.ButtonStyle.secondary)
    async def s2(self, _, interaction): await self.save(interaction, 2)
    @discord.ui.button(label="★★★", style=discord.ButtonStyle.secondary)
    async def s3(self, _, interaction): await self.save(interaction, 3)
    @discord.ui.button(label="★★★★", style=discord.ButtonStyle.secondary)
    async def s4(self, _, interaction): await self.save(interaction, 4)
    @discord.ui.button(label="★★★★★", style=discord.ButtonStyle.secondary)
    async def s5(self, _, interaction): await self.save(interaction, 5)

    async def save(self, interaction: discord.Interaction, stars: int):
        await interaction.response.send_message(f"Thanks! You rated {stars}/5 ⭐", ephemeral=True)
        await send_channel_safe(
            REVIEWS_CHANNEL_ID,
            embed=discord.Embed(
                title="⭐ Ticket Review",
                description=f"**User:** {interaction.user.mention}\n**Ticket:** `{self.channel_name}`\n**Rating:** {stars}/5",
                color=BLUE,
            )
        )
        self.disable_all_items()
        await interaction.message.edit(view=self)


@tree.command(name="ping", description="Check bot latency (Pong!).")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)
    await send_channel_safe(
        LOGS_CMD_USE_CHANNEL_ID,
        content=f"🧪 /ping by {interaction.user} ({interaction.user.id}) in {interaction.guild}"
    )


@tree.command(name="panel", description="Post the Nuvix ticket panel", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def panel_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=panel_embed(), view=PanelView(), ephemeral=False)


# Simple close command (inside the ticket channel)
ticket_group = app_commands.Group(name="ticket", description="Ticket commands")

@ticket_group.command(name="close", description="Close the current ticket.")
async def ticket_close(interaction: discord.Interaction, reason: str = "No response"):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await interaction.followup.send("Use this inside a ticket channel.", ephemeral=True)

    # Transcript
    file = await make_transcript(channel)
    await send_channel_safe(
        TRANSCRIPTS_CHANNEL_ID,
        content=f"🧾 Transcript for `{channel.name}` — closed by {interaction.user} ({interaction.user.id}) — Reason: {reason}",
        file=file
    )

    # DM review
    opener = None
    async for m in channel.history(limit=50, oldest_first=True):
        if not m.author.bot:
            opener = m.author
            break
    if opener:
        try:
            e = discord.Embed(
                title="🔒 Your ticket was closed",
                description=f"**Reason:** {reason}\n\nPlease rate your experience:",
                color=BLUE
            )
            if ICON_URL:
                e.set_author(name=BOT_NAME, icon_url=ICON_URL)
            await opener.send(embed=e, view=StarsView(channel.name))
        except Exception:
            pass

    await send_channel_safe(
        TICKETS_LOGS_CHANNEL_ID,
        content=f"🔒 Ticket `{channel.name}` closed by {interaction.user} — Reason: {reason}"
    )

    try:
        await channel.delete(reason=f"Closed by {interaction.user} — {reason}")
    except Exception as e:
        return await interaction.followup.send(f"Failed to delete channel: {e}", ephemeral=True)

    await interaction.followup.send("Ticket closed.", ephemeral=True)

tree.add_command(ticket_close.parent)


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    keep_alive()  # harmless on Render web services
    if not TOKEN:
        raise RuntimeError("NUVIX_TICKETS_TOKEN is not set.")
    bot.run(TOKEN)
