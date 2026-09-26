import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from anti_raid import AntiRaid

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("aishu")

TOKEN = os.getenv("DISCORD_TOKEN")


class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        await self.add_cog(AntiRaid(self))
        await self.tree.sync()

    async def on_ready(self):
        log.info("Aishu Anti-Raid online as %s (%s)", self.user, self.user.id)


bot = AishuBot()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

bot.run(TOKEN)
