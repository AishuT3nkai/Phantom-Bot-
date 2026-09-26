import logging
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

log = logging.getLogger("aishu.antiraid")

OWNER_ID = 1534184389838114857
SPAM_WINDOW = 5.0
SPAM_MESSAGE_LIMIT = 5
DUPLICATE_WINDOW = 10.0
DUPLICATE_LIMIT = 3
TIMEOUT_DURATION = timedelta(hours=1)


class AntiRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_times = defaultdict(deque)
        self.recent_content = defaultdict(deque)
        self.flagged = set()

    def _is_exempt(self, message: discord.Message) -> bool:
        if message.author.bot or not message.guild:
            return True
        perms = message.author.guild_permissions
        return perms.administrator or perms.manage_guild or perms.moderate_members

    def _is_spam(self, message: discord.Message) -> bool:
        key = (message.guild.id, message.author.id)
        now = time.monotonic()

        times = self.message_times[key]
        while times and now - times[0] > SPAM_WINDOW:
            times.popleft()
        times.append(now)

        if len(times) >= SPAM_MESSAGE_LIMIT:
            return True

        content = message.content.strip().lower()
        if not content:
            return False

        recent = self.recent_content[key]
        while recent and now - recent[0][0] > DUPLICATE_WINDOW:
            recent.popleft()
        recent.append((now, content))

        duplicates = sum(1 for _, value in recent if value == content)
        return duplicates >= DUPLICATE_LIMIT

    async def _notify_owner(
        self,
        message: discord.Message,
        timeout_until: discord.utils.MISSING,
    ):
        owner = self.bot.get_user(OWNER_ID)
        if owner is None:
            try:
                owner = await self.bot.fetch_user(OWNER_ID)
            except discord.HTTPException:
                return

        try:
            await owner.send(
                f"⚠️ Spam detection\n"
                f"User: {message.author} ({message.author.id})\n"
                f"Server: {message.guild.name} ({message.guild.id})\n"
                f"Channel: #{message.channel.name}\n"
                f"Action: 1-hour timeout\n"
                f"Reason: spam detected"
            )
        except discord.HTTPException:
            log.warning("Could not DM owner %s", OWNER_ID)

    async def _timeout(self, message: discord.Message):
        member = message.author
        if not isinstance(member, discord.Member):
            return

        if member.id in self.flagged:
            return
        self.flagged.add(member.id)

        me = message.guild.me
        if not me or not me.guild_permissions.moderate_members:
            log.error(
                "Cannot timeout %s in guild %s: missing Moderate Members permission",
                member,
                message.guild.id,
            )
            self.flagged.discard(member.id)
            return

        if member.top_role >= me.top_role:
            log.warning(
                "Cannot timeout %s in guild %s because of role hierarchy",
                member,
                message.guild.id,
            )
            self.flagged.discard(member.id)
            return

        try:
            await member.timeout(
                TIMEOUT_DURATION,
                reason="Aishu anti-spam: message spam detected",
            )
            await self._notify_owner(message, discord.utils.MISSING)

            try:
                await message.channel.send(
                    f"{member.mention} has been timed out for **1 hour** for spam.",
                    delete_after=8,
                )
            except discord.HTTPException:
                pass

            log.warning(
                "Timed out %s (%s) for 1 hour in guild %s",
                member,
                member.id,
                message.guild.id,
            )
        except discord.Forbidden:
            log.exception(
                "Discord denied timeout for %s (%s) in guild %s",
                member,
                member.id,
                message.guild.id,
            )
        except discord.HTTPException:
            log.exception(
                "Discord API error while timing out %s (%s)",
                member,
                member.id,
            )
        finally:
            self.flagged.discard(member.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self._is_exempt(message):
            return

        if self._is_spam(message):
            await self._timeout(message)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and isinstance(message.author, discord.Member):
            key = (message.guild.id, message.author.id)
            self.recent_content.pop(key, None)


async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
