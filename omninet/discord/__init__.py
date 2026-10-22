"""The Discord relay: battle rooms and account links for Omnipet, through a Discord bot.

Ported from the standalone bot (E:/DiscordBot/discord_relay_bot.py, an aiohttp
server on port 5000 beside a discord.py client) into Omninet, owner 2026-10-17.
It loads only when ``DISCORD_BOT_TOKEN`` is set: without a token the routes
are not mounted and discord.py is never imported.

    relay.py   the state: game rooms, channel rooms (!host / !join), links
    bot.py     the discord.py client: commands, battle-data embeds, cleanup
    routes/discord.py   the HTTP API the game calls, /api/v1/discord/...

Run the bot on one environment only: a token connected twice answers every
command twice.
"""
