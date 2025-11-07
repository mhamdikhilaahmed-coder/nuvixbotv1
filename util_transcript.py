import io
import discord
async def build_text_transcript(channel: discord.TextChannel) -> discord.File:
    lines = []
    async for msg in channel.history(limit=2000, oldest_first=True):
        t = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content.replace("\n", "\\n")
        lines.append(f"[{t}] {author}: {content}")
        for a in msg.attachments:
            lines.append(f"    [attachment] {a.filename} -> {a.url}")
    txt = "\n".join(lines) if lines else "No messages."
    buf = io.BytesIO(txt.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.txt")
async def build_html_transcript(channel: discord.TextChannel) -> discord.File:
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Transcript</title>",
        "<style>body{font-family:Inter,Arial,sans-serif;background:#0b1220;color:#e6edf3;padding:20px}",
        ".m{margin:8px 0}.a{color:#9bbcff}.t{color:#6aa1ff;font-size:12px}.c{white-space:pre-wrap}",
        "</style></head><body>",
        f"<h2>Transcript — #{channel.name}</h2>"
    ]
    async for msg in channel.history(limit=2000, oldest_first=True):
        t = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author} ({msg.author.id})"
        parts.append(f"<div class='m'><div class='a'>{author}</div><div class='t'>{t}</div><div class='c'>{discord.utils.escape_markdown(msg.content)}</div>")
        if msg.attachments:
            parts.append("<ul>")
            for a in msg.attachments:
                parts.append(f"<li><a href='{a.url}' target='_blank'>{a.filename}</a></li>")
            parts.append("</ul>")
        parts.append("</div>")
    parts.append("</body></html>")
    html = "\n".join(parts)
    buf = io.BytesIO(html.encode("utf-8"))
    return discord.File(buf, filename=f"transcript_{channel.id}.html")
