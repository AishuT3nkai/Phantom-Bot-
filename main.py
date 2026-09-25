import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
import wavelink

import database
from music_core import Music
from advanced_music import AdvancedMusic
from search_music import SearchMusic

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("DISCORD_TOKEN")
LAVALINK_URI = os.getenv("LAVALINK_URI", "http://127.0.0.1:2333")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "change-this-password")
LAVALINK_IDENTIFIER = os.getenv("LAVALINK_IDENTIFIER", "PHANTOM")

class Phantom(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self._restored_247 = False

    async def setup_hook(self):
        database.init_db()
        node = wavelink.Node(
            uri=LAVALINK_URI,
            password=LAVALINK_PASSWORD,
            identifier=LAVALINK_IDENTIFIER
        )
        await wavelink.Pool.connect(
            nodes=[node],
            client=self,
            cache_capacity=100
        )
        await self.add_cog(Music(self))
        await self.add_cog(AdvancedMusic(self))
        await self.add_cog(SearchMusic(self))
        await self.tree.sync()

    async def on_ready(self):
        logging.info("Phantom online: %s (%s)", self.user, self.user.id)
        if not self._restored_247:
            cog = self.get_cog("Music")
            if cog:
                self._restored_247 = True
                await cog.restore_all_247()

    async def on_wavelink_node_ready(self, payload):
        logging.info("Lavalink ready: %s", payload.node)

    async def on_wavelink_node_disconnected(self, payload):
        logging.warning("Lavalink node disconnected: %s", payload.node)

bot = Phantom()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

bot.run(TOKEN)
