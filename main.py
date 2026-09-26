import logging
import os
from urllib.parse import urlparse

import discord
from discord.ext import commands
from dotenv import load_dotenv
import wavelink

load_dotenv()

import database
from music_core import Music
from advanced_music import AdvancedMusic
from search_music import SearchMusic

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("phantom")

TOKEN = os.getenv("DISCORD_TOKEN")

PUBLIC_LAVALINK_URI = "https://lavalinkv4.serenetia.com"
PUBLIC_LAVALINK_PASSWORD = "https://dsc.gg/ajidevserver"

def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

raw_uri = os.getenv("LAVALINK_URI", "").strip()
raw_password = os.getenv("LAVALINK_PASSWORD", "").strip()
use_local = env_bool("LAVALINK_USE_LOCAL", False)

# A stale Nexus variable such as 127.0.0.1:2333 must not break a mobile deployment.
if (
    not raw_uri
    or raw_uri.lower() in {"http://127.0.0.1:2333", "http://localhost:2333"}
) and not use_local:
    LAVALINK_URI = PUBLIC_LAVALINK_URI
    LAVALINK_PASSWORD = (
        PUBLIC_LAVALINK_PASSWORD
        if not raw_password or raw_password == "change-this-password"
        else raw_password
    )
else:
    LAVALINK_URI = raw_uri or "http://127.0.0.1:2333"
    LAVALINK_PASSWORD = raw_password or "change-this-password"

LAVALINK_IDENTIFIER = os.getenv("LAVALINK_IDENTIFIER", "PHANTOM").strip() or "PHANTOM"

parsed_uri = urlparse(LAVALINK_URI)
LAVALINK_SECURE = env_bool(
    "LAVALINK_SECURE",
    parsed_uri.scheme.lower() in {"https", "wss"},
)

if parsed_uri.scheme.lower() not in {"http", "https"}:
    raise RuntimeError(
        "LAVALINK_URI must start with http:// or https:// "
        f"(got {LAVALINK_URI!r})"
    )

class Phantom(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        database.init_db()

        node = wavelink.Node(
            uri=LAVALINK_URI,
            password=LAVALINK_PASSWORD,
            identifier=LAVALINK_IDENTIFIER,
            secure=LAVALINK_SECURE,
            retries=None,
        )
        log.info(
            "Connecting to Lavalink node %s (%s, secure=%s)",
            LAVALINK_IDENTIFIER,
            parsed_uri.netloc or parsed_uri.path,
            LAVALINK_SECURE,
        )

        await wavelink.Pool.connect(
            nodes=[node],
            client=self,
            cache_capacity=100,
        )

        await self.add_cog(Music(self))
        await self.add_cog(AdvancedMusic(self))
        await self.add_cog(SearchMusic(self))
        await self.tree.sync()

    async def on_ready(self):
        log.info("Phantom online: %s (%s)", self.user, self.user.id)
        cog = self.get_cog("Music")
        if cog:
            await cog.restore_all_247()

    async def on_wavelink_node_ready(self, payload):
        log.info("Lavalink ready: %s", payload.node)
        cog = self.get_cog("Music")
        if cog:
            await cog.restore_all_247()

    async def on_wavelink_node_disconnected(self, payload):
        log.warning("Lavalink node disconnected: %s", payload.node)

bot = Phantom()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

bot.run(TOKEN)
