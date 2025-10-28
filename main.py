import os
import discord
from discord.ext import commands
from datetime import datetime

# === CONFIGURATION ===
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for join events

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.event
async def on_member_join(member):
    # 👇 Replace with the ID of your welcome channel
    channel_id = 1432475296522829844  # Example channel ID (replace with yours)
    channel = bot.get_channel(1432474691381104707)

    if channel:
        join_date = datetime.now().strftime("%B %d, %Y • %H:%M")

        # Create the embed message
        embed = discord.Embed(
            title="👋 A new user has joined!",
            description=f"Hey {member.mention}, welcome to **Nuvix Market** 💫",
            color=discord.Color.from_rgb(130, 80, 255)  # Neon purple-blue
        )

        embed.add_field(name="👤 User", value=f"{member.mention}", inline=True)
        embed.add_field(name="📅 Joined On", value=join_date, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)

        # 👇 Banner (hosted image)
        embed.set_image(
            url="https://discord.com/channels/774256913646878752/1432475296522829844/1432708362465706056"
        )

        embed.set_footer(text="Welcome System — Nuvix Market 💎")
        await channel.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! Nuvix Market bot is online and ready.")

# === RUN BOT ===
bot.run(os.getenv("TOKEN"))
