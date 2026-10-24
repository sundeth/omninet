"""The discord.py client of the relay: commands, battle-data embeds, cleanup.

Imported only when ``DISCORD_BOT_TOKEN`` is set (main.py), so a server without
a token never needs discord.py. Commands, as the standalone bot had them:

    !link [TamerName]   a pairing code for the game, sent by DM
    !unlink, !whoami    the caller's link
    !users              every link
    !host CODE [name]   a 6-digit channel room;  !join CODE [name]
    !data CODE {json}   a side's battle data;    !getdata CODE   the other side's
    !status             the open channel rooms

Battle data can also come as an embed (a webhook's "Battle Data: CODE" with a
```json block); when both sides are in, the bot posts both, and when the data
carries a simulation result it edits in the winner 45 seconds later (the
animation's length).
"""
from __future__ import annotations

import asyncio
import json
import re

from omninet.discord.relay import Relay

RESULT_DELAY_SECONDS = 45
CLEANUP_SECONDS = 300


def create_bot(relay: Relay):
    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    rooms = relay.channel_rooms

    async def post_both_sides(channel, code: str, room: dict) -> None:
        await channel.send(f"🎊 **Battle Ready for room `{code}`!**")
        for title, key in (("Guest Data", "guest_data"), ("Host Data", "host_data")):
            embed = discord.Embed(title=title, description=f"||```json\n{json.dumps(room[key])}\n```||",
                                  color=0x3498DB)
            # The room code in the text is what the game's filter looks for
            await channel.send(f"**Room {code} {title}:**", embed=embed)

    async def announce_result(code: str, result: dict) -> None:
        await asyncio.sleep(RESULT_DELAY_SECONDS)
        room = rooms.rooms.get(code)
        if room is None:
            return
        winner = result.get("winner", 0)
        if winner in (1, 2):
            name = room.get("host_name" if winner == 1 else "guest_name") or ("Host" if winner == 1 else "Guest")
            emoji, text, color = "🏆", f"{'HOST' if winner == 1 else 'GUEST'} WINS! ({name})", 0x00FF00
        else:
            emoji, text, color = "🤝", "DRAW!", 0xFFFF00
        channel = bot.get_channel(room["channel_id"])
        if channel is None:
            return
        async for message in channel.history(limit=50):
            if message.embeds and f"Battle Data: {code}" in (message.content or ""):
                embed = discord.Embed(title=f"{emoji} Battle Complete!", description=f"**{text}**", color=color)
                embed.set_footer(text=f"Room {code} • Omnipet")
                await message.edit(embed=embed)
                await channel.send(f"{emoji} Battle finished! {text}")
                break

    async def receive(channel, code: str, battle_data: dict) -> None:
        room = rooms.put_data(code, battle_data)
        if room is None:
            return
        await post_both_sides(channel, code, room)
        if "simulation_result" in battle_data:
            bot.loop.create_task(announce_result(code, battle_data["simulation_result"]))

    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(CLEANUP_SECONDS)
            rooms.cleanup()
            relay.game_rooms.cleanup()

    @bot.event
    async def on_ready():
        relay.bot_ready = True
        print(f"[Discord] Logged in as {bot.user.name}")
        if not getattr(bot, "_cleanup_started", False):
            bot._cleanup_started = True
            bot.loop.create_task(cleanup_loop())

    @bot.event
    async def on_disconnect():
        relay.bot_ready = False

    @bot.event
    async def on_resumed():
        # A dropped gateway connection resumes without a second on_ready:
        # without this /health said "connecting" while the bot answered.
        relay.bot_ready = True

    @bot.event
    async def on_message(message):
        await bot.process_commands(message)
        # Battle data posted as an embed, by a webhook or a bot
        if not message.embeds or not (message.webhook_id or message.author.bot):
            return
        match = re.search(r"Battle Data: (\d{6})", message.content or "")
        if not match:
            return
        code = match.group(1)
        for embed in message.embeds:
            text = embed.description or ""
            start, end = text.find("{"), text.rfind("}")
            if "```json" not in text or start == -1 or end < start:
                continue
            try:
                battle_data = json.loads(text[start:end + 1].replace("||", ""))
            except ValueError:
                continue
            if not battle_data.get("type"):
                continue
            rooms.ensure(code, message.channel.id)
            await receive(message.channel, code, battle_data)

    @bot.command(name="host")
    async def host_battle(ctx, code: str = None, username: str = "Tamer"):
        why = rooms.host(code, ctx.author.id, username, ctx.channel.id)
        await ctx.send(f"❌ {why}" if why else f"✅ Room `{code}` created!\nHost: **{username}**")

    @bot.command(name="join")
    async def join_battle(ctx, code: str = None, username: str = "Tamer"):
        why = rooms.join(code, ctx.author.id, username)
        if why:
            await ctx.send(f"❌ {why}")
            return
        await ctx.send(f"✅ Joined room `{code}`!\nGuest: **{username}**")

    @bot.command(name="data")
    async def send_battle_data(ctx, code: str, *, data: str):
        if code not in rooms.rooms:
            await ctx.send(f"❌ Room `{code}` not found")
            return
        try:
            battle_data = json.loads(data)
        except ValueError:
            await ctx.send("❌ Invalid JSON")
            return
        kind = battle_data.get("type")
        if kind not in ("host_data", "guest_data"):
            return
        await ctx.send(f"✅ {'Host' if kind == 'host_data' else 'Guest'} data received for room `{code}`")
        await receive(ctx.channel, code, battle_data)

    @bot.command(name="getdata")
    async def get_opponent_data(ctx, code: str):
        room = rooms.rooms.get(code)
        if room is None:
            return
        if ctx.author.id == room["host"] and room["guest_data"]:
            await ctx.send(f"```json\n{json.dumps(room['guest_data'])}\n```")
        elif ctx.author.id == room["guest"] and room["host_data"]:
            await ctx.send(f"```json\n{json.dumps(room['host_data'])}\n```")

    @bot.command(name="status")
    async def check_status(ctx):
        if not rooms.rooms:
            await ctx.send("No active rooms")
            return
        lines = [f"• Room `{code}`: {room['host_name']} vs {room.get('guest_name') or 'Waiting...'}"
                 for code, room in rooms.rooms.items()]
        await ctx.send("**Active Rooms:**\n" + "\n".join(lines))

    @bot.command(name="link")
    async def link_account(ctx, *, tamer_name: str = None):
        code = relay.links.create(ctx.author.id, ctx.author.name, tamer_name or ctx.author.name)
        try:
            await ctx.author.send(f"**Your Pairing Code:** `{code}`\nEnter this code in your Omnipet game.")
            await ctx.send(f"✅ Code sent to your DMs! Check messages from {bot.user.name}.")
        except discord.Forbidden:
            await ctx.send(f"⚠️ Could not send DM. Please enable DMs.\nYour code is: ||`{code}`||")

    @bot.command(name="unlink")
    async def unlink_account(ctx):
        data = relay.links.remove_user(ctx.author.id)
        await ctx.send(f"✅ Unlinked account **{data['tamer_name']}**" if data else "❌ No linked account found")

    @bot.command(name="whoami")
    async def whoami(ctx):
        found = relay.links.find_user(ctx.author.id)
        if not found:
            await ctx.send("❌ No linked account found\nUse `!link TamerName` to link")
            return
        code, data = found
        await ctx.send(f"**Your Linked Account:**\n🎮 Tamer: **{data['tamer_name']}**\n🔗 Code: `{code}`\n"
                       f"📅 Linked: {data['linked_at'][:16].replace('T', ' ')}")

    @bot.command(name="users")
    async def list_users(ctx):
        if not relay.links.links:
            await ctx.send("No linked users yet")
            return
        lines = [f"• `{code}`: **{d['tamer_name']}** (@{d['username']})"
                 for code, d in sorted(relay.links.links.items())]
        await ctx.send("**Linked Users:**\n" + "\n".join(lines))

    return bot


async def run_bot(token: str, relay: Relay) -> None:
    """Connect and serve until cancelled (Omninet's lifespan)."""
    bot = create_bot(relay)
    try:
        await bot.start(token)
    except asyncio.CancelledError:
        raise
    except Exception as exc:          # a bad token or Discord down: the API goes on
        print(f"[Discord] bot stopped: {exc}")
    finally:
        relay.bot_ready = False
        if not bot.is_closed():
            await bot.close()
