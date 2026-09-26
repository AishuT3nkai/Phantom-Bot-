import asyncio
import logging
import re

import discord
from discord.ext import commands
import wavelink

from database import (
    add_favorite, add_history, clear_queue_state, get_favorites,
    get_history, get_settings, load_queue_state, remove_favorite,
    save_queue_state, set_setting
)

URL_RE = re.compile(r"^https?://", re.I)
MENTION_DOT_RE = re.compile(r"^<@!?(\d+)>\.$")
SEARCH_PREFIXES = ("ytmsearch:", "ytsearch:", "scsearch:", "dzsearch:", "spsearch:", "amsearch:", "tdsearch:", "qbsearch:", "jssearch:", "ymsearch:")

class State:
    def __init__(self):
        self.message = None
        self.channel = None
        self.requester_id = None
        self.requester = "Unknown"
        self.ticker = None
        self.recover = None
        self.lock = asyncio.Lock()
        self.retry = 0

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}
        bot.add_view(Controls(self))

    def state(self, guild_id):
        return self.states.setdefault(guild_id, State())

    def player(self, guild):
        player = guild.voice_client
        if isinstance(player, wavelink.Player) and player.connected:
            return player
        return None

    def reason_name(self, reason):
        return getattr(reason, "name", str(reason)).lower().replace("trackendreason.", "")

    async def can_control(self, interaction, notify=True):
        if not interaction.guild:
            if notify:
                await interaction.response.send_message("Server only.", ephemeral=True)
            return False
        _, _, dj_role, _, _ = get_settings(interaction.guild.id)
        if dj_role is not None:
            roles = getattr(interaction.user, "roles", [])
            allowed = (
                interaction.user.guild_permissions.manage_guild
                or interaction.user.guild_permissions.administrator
                or any(role.id == dj_role for role in roles)
            )
        else:
            allowed = True
        if not allowed:
            if notify:
                await interaction.response.send_message(
                    "DJ role or Manage Server permission required.", ephemeral=True
                )
            return False
        player = self.player(interaction.guild)
        if player and interaction.user.voice and player.channel != interaction.user.voice.channel:
            if not interaction.user.guild_permissions.manage_guild:
                if notify:
                    await interaction.response.send_message(
                        "Join my voice channel first.", ephemeral=True
                    )
                return False
        return True

    async def ensure(self, interaction):
        if not interaction.guild or not interaction.user.voice:
            raise RuntimeError("Join a voice channel first.")
        if not await self.can_control(interaction, notify=False):
            raise RuntimeError("DJ role or Manage Server permission required.")
        player = self.player(interaction.guild)
        if player and player.channel != interaction.user.voice.channel:
            raise RuntimeError("Phantom is already in another voice channel.")
        if not player:
            try:
                player = await interaction.user.voice.channel.connect(
                    cls=wavelink.Player,
                    timeout=20,
                    reconnect=True,
                )
            except Exception as exc:
                log.exception("Voice connection failed in guild %s", interaction.guild.id)
                raise RuntimeError(
                    "I could not connect to that voice channel. Check my Connect and Speak permissions."
                ) from exc
        volume, _, _, autoplay, _ = get_settings(interaction.guild.id)
        await player.set_volume(volume)
        player.autoplay = wavelink.AutoPlayMode.enabled if autoplay else wavelink.AutoPlayMode.disabled
        return player

    async def resolve(self, query):
        query = query.strip()
        attempts = []
        if URL_RE.match(query):
            attempts.append(query)
        else:
            attempts.extend(SEARCH_PREFIXES[i] + query for i in range(len(SEARCH_PREFIXES)))
            attempts.append(query)
        seen = set()
        for attempt in attempts:
            if attempt in seen:
                continue
            seen.add(attempt)
            try:
                result = await wavelink.Playable.search(attempt)
            except Exception:
                continue
            if result:
                return result
        return None

    async def resolve_track(self, query):
        result = await self.resolve(query)
        if result and not isinstance(result, wavelink.Playlist):
            return result[0]
        return None

    def tag_values(self, track, requester, requester_id):
        try:
            extras = dict(getattr(track, "extras", {}) or {})
        except (TypeError, ValueError):
            extras = {}
        extras["requester"] = str(requester or "Unknown")
        extras["requester_id"] = int(requester_id) if requester_id is not None else None
        track.extras = extras
        return track

    def tag(self, track, interaction):
        return self.tag_values(track, interaction.user.display_name, interaction.user.id)

    def track_requester(self, track, default_name="Unknown", default_id=None):
        try:
            extras = dict(getattr(track, "extras", {}) or {})
        except (TypeError, ValueError):
            extras = {}
        return (
            extras.get("requester", default_name),
            extras.get("requester_id", default_id),
        )

    async def save_state(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        player = self.player(guild)
        state = self.state(guild_id)
        old = load_queue_state(guild_id)
        if not player or not player.channel:
            if old:
                return
            clear_queue_state(guild_id)
            return
        text_id = state.channel.id if state.channel else (old or {}).get("text_channel_id")
        save_queue_state(
            guild_id,
            player.channel.id,
            text_id,
            state.requester_id or (old or {}).get("requester_id"),
            state.requester or (old or {}).get("requester", "Unknown"),
            player.current,
            getattr(player, "position", 0),
            list(player.queue),
        )

    async def show_card(self, guild):
        player = self.player(guild)
        state = self.state(guild.id)
        if not player or not player.current or not state.channel:
            return
        async with state.lock:
            if state.message:
                try:
                    await state.message.delete()
                except discord.HTTPException:
                    pass
            from card import render_card
            image = await render_card(player.current, player.position, state.requester, player.paused)
            state.message = await state.channel.send(
                file=discord.File(image, "phantom-music.jpg"),
                view=Controls(self)
            )

    async def tick(self, guild_id):
        try:
            while True:
                await asyncio.sleep(15)
                guild = self.bot.get_guild(guild_id)
                player = self.player(guild) if guild else None
                if not guild or not player or not player.current:
                    return
                await self.show_card(guild)
                await self.save_state(guild_id)
        except asyncio.CancelledError:
            return

    async def start_ticker(self, guild_id):
        state = self.state(guild_id)
        if state.ticker and not state.ticker.done():
            state.ticker.cancel()
        state.ticker = asyncio.create_task(self.tick(guild_id))

    async def recover_voice(self, guild_id):
        return await self.restore_saved(guild_id, require_247=True)

    async def restore_saved(self, guild_id, *, require_247=False):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        _, _, _, autoplay, stay = get_settings(guild_id)
        if require_247 and not stay:
            return False

        if self.player(guild):
            return True

        saved = load_queue_state(guild_id)
        if not saved:
            return False

        channel = guild.get_channel(saved.get("voice_channel_id"))
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return False

        stale = guild.voice_client
        if isinstance(stale, wavelink.Player) and not stale.connected:
            try:
                await stale.disconnect()
            except Exception:
                pass

        try:
            player = await channel.connect(cls=wavelink.Player)
            await player.set_volume(get_settings(guild_id)[0])
            player.autoplay = (
                wavelink.AutoPlayMode.enabled
                if autoplay else wavelink.AutoPlayMode.disabled
            )

            state = self.state(guild_id)
            state.requester_id = saved.get("requester_id")
            state.requester = saved.get("requester") or "Unknown"

            text_id = saved.get("text_channel_id")
            state.channel = guild.get_channel(text_id) if text_id else None

            for data in saved.get("queue", []):
                query = data.get("uri") or data.get("title", "")
                track = await self.resolve_track(query)
                if track:
                    self.tag_values(
                        track,
                        data.get("requester", state.requester),
                        data.get("requester_id", state.requester_id),
                    )
                    player.queue.put(track)

            current_data = saved.get("current")
            if current_data:
                query = current_data.get("uri") or current_data.get("title", "")
                track = await self.resolve_track(query)
                if track:
                    requester, requester_id = self.track_requester(
                        track, state.requester, state.requester_id
                    )
                    self.tag_values(track, requester, requester_id)
                    await player.play(track, volume=get_settings(guild_id)[0])
                    position = max(
                        0,
                        min(
                            int(saved.get("current_position", 0) or 0),
                            max(0, int(track.length or 0) - 1000),
                        ),
                    )
                    if position > 0 and track.is_seekable:
                        await player.seek(position)
            elif player.queue:
                await player.play(
                    player.queue.get(),
                    volume=get_settings(guild_id)[0],
                )

            if player.current:
                await self.start_ticker(guild_id)
            await self.save_state(guild_id)
            return True
        except Exception:
            log.exception("Failed to restore saved music state for guild %s", guild_id)
            return False

    async def restore_all_247(self):
        for guild in self.bot.guilds:
            if get_settings(guild.id)[4]:
                await self.recover_voice(guild.id)

    async def previous_track(self, guild):
        player = self.player(guild)
        if player:
            history = list(player.queue.history)
            if player.current and len(history) > 1 and history[-1].identifier == player.current.identifier:
                return history[-2]
            if history:
                return history[-1]
        rows = get_history(guild.id, 5)
        if rows:
            return await self.resolve_track(rows[1][2] or rows[1][0]) if len(rows) > 1 else await self.resolve_track(rows[0][2] or rows[0][0])
        return None

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload):
        player = payload.player
        if not player or not player.guild or not player.current:
            return
        state = self.state(player.guild.id)
        state.requester, state.requester_id = self.track_requester(
            player.current,
            state.requester,
            state.requester_id,
        )
        state.retry = 0
        add_history(player.guild.id, state.requester_id, player.current)
        await self.save_state(player.guild.id)
        await self.show_card(player.guild)
        await self.start_ticker(player.guild.id)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        player = payload.player
        if not player or not player.guild or self.reason_name(payload.reason) != "finished":
            return
        if player.autoplay != wavelink.AutoPlayMode.disabled:
            return
        try:
            next_track = player.queue.get()
        except wavelink.QueueEmpty:
            next_track = None
        if next_track:
            try:
                await player.play(next_track, volume=get_settings(player.guild.id)[0])
            except Exception:
                log.exception("Failed to start next track in guild %s", player.guild.id)
        else:
            clear_queue_state(player.guild.id)
            state = self.state(player.guild.id)
            if state.ticker and not state.ticker.done():
                state.ticker.cancel()
            if state.message:
                try:
                    await state.message.delete()
                except discord.HTTPException:
                    pass
                state.message = None

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload):
        player = payload.player
        if not player or not player.guild:
            return
        state = self.state(player.guild.id)
        if state.retry >= 2:
            state.retry = 0
            try:
                await player.skip(force=True)
            except Exception:
                log.exception("Failed to skip errored track in guild %s", player.guild.id)
            return

        state.retry += 1
        track = await self.resolve_track(
            f"{payload.track.title} {payload.track.author}"
        )
        if track:
            self.tag_values(track, state.requester, state.requester_id)
            try:
                await player.play(track, volume=get_settings(player.guild.id)[0])
            except Exception:
                log.exception("Failed to retry track in guild %s", player.guild.id)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload):
        if payload.player:
            try:
                await payload.player.skip(force=True)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload):
        player = payload.player
        if not player or not player.guild or not get_settings(player.guild.id)[4]:
            return
        state = self.state(player.guild.id)
        if not state.recover or state.recover.done():
            state.recover = asyncio.create_task(self._delayed_recover(player.guild.id))

    async def _delayed_recover(self, guild_id):
        await asyncio.sleep(5)
        await self.recover_voice(guild_id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.bot.user or member.id != self.bot.user.id or not before.channel or after.channel:
            return
        if not get_settings(before.channel.guild.id)[4]:
            return
        state = self.state(before.channel.guild.id)
        if not state.recover or state.recover.done():
            state.recover = asyncio.create_task(self._delayed_recover(before.channel.guild.id))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            await self.bot.process_commands(message)
            return
        raw = message.content.strip()
        member = None
        mention = MENTION_DOT_RE.match(raw)
        if mention:
            member = message.guild.get_member(int(mention.group(1)))
        elif raw.startswith("@") and raw.endswith("."):
            name = raw[1:-1].strip().lower()
            member = discord.utils.find(
                lambda item: item.name.lower() == name or item.display_name.lower() == name,
                message.guild.members
            )
        if member:
            rows = get_favorites(member.id, message.guild.id)
            if rows:
                text = [f"{member.display_name}'s Favorites"]
                text.extend(f"{n:02}. {row[0]} — {row[1]}" for n, row in enumerate(rows[:25], 1))
                content = "\n".join(text)
                if len(content) > 1900:
                    content = content[:1890] + "\n..."
                await message.channel.send(content)
            else:
                await message.channel.send(f"{member.display_name} has no favorites here.")
        await self.bot.process_commands(message)

    @commands.hybrid_command(name="play", description="Play a song, URL or playlist.")
    async def play(self, interaction, *, query: str):
        try:
            player = await self.ensure(interaction)
        except RuntimeError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)
        try:
            result = await self.resolve(query)
        except Exception:
            log.exception("Track search failed in guild %s", interaction.guild.id)
            return await interaction.response.send_message(
                "Music search is temporarily unavailable.", ephemeral=True
            )
        if not result:
            return await interaction.response.send_message("No tracks found.", ephemeral=True)
        state = self.state(interaction.guild.id)
        state.channel = interaction.channel
        state.requester_id = interaction.user.id
        state.requester = interaction.user.display_name
        volume, max_queue, _, autoplay, _ = get_settings(interaction.guild.id)
        player.autoplay = wavelink.AutoPlayMode.enabled if autoplay else wavelink.AutoPlayMode.disabled
        if isinstance(result, wavelink.Playlist):
            tracks = list(result.tracks)[:max(0, max_queue - player.queue.count)]
            for track in tracks:
                self.tag(track, interaction)
                player.queue.put(track)
            message = f"Added {len(tracks)} tracks from {result.name}."
        else:
            if player.queue.count >= max_queue:
                return await interaction.response.send_message("Queue is full.", ephemeral=True)
            self.tag(result[0], interaction)
            player.queue.put(result[0])
            message = f"Added {result[0].title} — {result[0].author}."
        if not player.playing and player.queue:
            await player.play(player.queue.get(), volume=volume)
        await self.save_state(interaction.guild.id)
        await interaction.response.send_message(message, ephemeral=True)

    @commands.hybrid_command(name="join", description="Join your voice channel.")
    async def join(self, interaction):
        try:
            player = await self.ensure(interaction)
        except RuntimeError as exc:
            return await interaction.response.send_message(str(exc), ephemeral=True)
        await interaction.response.send_message(f"Joined {player.channel.name}.", ephemeral=True)

    @commands.hybrid_command(name="pause", description="Pause playback.")
    async def pause(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await player.pause(True)
        await self.save_state(interaction.guild.id)
        await interaction.response.send_message("Paused.", ephemeral=True)
        await self.show_card(interaction.guild)

    @commands.hybrid_command(name="resume", description="Resume playback.")
    async def resume(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await player.pause(False)
        await self.save_state(interaction.guild.id)
        await interaction.response.send_message("Resumed.", ephemeral=True)
        await self.show_card(interaction.guild)

    @commands.hybrid_command(name="skip", description="Skip the current song.")
    async def skip(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await player.skip(force=True)
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @commands.hybrid_command(name="stop", description="Stop and clear the queue.")
    async def stop(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        player.queue.clear()
        await player.stop()
        clear_queue_state(interaction.guild.id)
        state = self.state(interaction.guild.id)
        if state.ticker and not state.ticker.done():
            state.ticker.cancel()
        if state.message:
            try:
                await state.message.delete()
            except discord.HTTPException:
                pass
            state.message = None
        await interaction.response.send_message("Stopped and cleared.", ephemeral=True)

    @commands.hybrid_command(name="queue", description="Show the queue.")
    async def queue(self, interaction):
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        lines = [f"Now: {player.current.title} — {player.current.author}"] if player.current else []
        lines.extend(f"{n:02}. {track.title} — {track.author}" for n, track in enumerate(list(player.queue)[:25], 1))
        lines.append(f"Queued: {player.queue.count}")
        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1890] + "\n..."
        await interaction.response.send_message(content, ephemeral=True)

    @commands.hybrid_command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        player.queue.shuffle()
        await self.save_state(interaction.guild.id)
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)

    @commands.hybrid_command(name="volume", description="Set volume from 0 to 100.")
    async def volume(self, interaction, value: int):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        value = max(0, min(100, value))
        await player.set_volume(value)
        set_setting(interaction.guild.id, "default_volume", value)
        await self.save_state(interaction.guild.id)
        await interaction.response.send_message(f"Volume: {value}%.", ephemeral=True)

    @commands.hybrid_command(name="leave", description="Leave the voice channel.")
    async def leave(self, interaction):
        if not await self.can_control(interaction):
            return
        player = self.player(interaction.guild)
        if player:
            await player.disconnect()
        if not get_settings(interaction.guild.id)[4]:
            clear_queue_state(interaction.guild.id)
        await interaction.response.send_message("Disconnected.", ephemeral=True)

    @commands.hybrid_command(name="favorite", description="Favorite the current song.")
    async def favorite(self, interaction):
        player = self.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        add_favorite(interaction.user.id, interaction.guild.id, player.current)
        await interaction.response.send_message("Added to your favorites.", ephemeral=True)

    @commands.hybrid_command(name="unfavorite", description="Remove the current song from your favorites.")
    async def unfavorite(self, interaction):
        player = self.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        remove_favorite(interaction.user.id, interaction.guild.id, player.current.identifier)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @commands.hybrid_command(name="favorites", description="View a user's favorites.")
    async def favorites(self, interaction, member: discord.Member = None):
        member = member or interaction.user
        rows = get_favorites(member.id, interaction.guild.id)
        if not rows:
            return await interaction.response.send_message(f"{member.display_name} has no favorites.", ephemeral=True)
        lines = [f"{member.display_name}'s Favorites"]
        lines.extend(f"{n:02}. {row[0]} — {row[1]}" for n, row in enumerate(rows[:25], 1))
        content = "\n".join(lines)
        if len(content) > 1900:
            content = content[:1890] + "\n..."
        await interaction.response.send_message(content)

class Controls(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction):
        return await self.cog.can_control(interaction)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, custom_id="phantom:pause")
    async def pause(self, interaction, button):
        player = self.cog.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await interaction.response.defer()
        await player.pause(not player.paused)
        await self.cog.save_state(interaction.guild.id)
        await self.cog.show_card(interaction.guild)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="phantom:previous")
    async def previous(self, interaction, button):
        track = await self.cog.previous_track(interaction.guild)
        if not track:
            return await interaction.response.send_message("No previous track.", ephemeral=True)
        player = self.cog.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Music player is no longer connected.", ephemeral=True)
        await interaction.response.defer()
        await player.play(track, volume=get_settings(interaction.guild.id)[0])
        await self.cog.save_state(interaction.guild.id)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="phantom:skip")
    async def skip(self, interaction, button):
        player = self.cog.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await interaction.response.defer()
        await player.skip(force=True)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="phantom:shuffle")
    async def shuffle(self, interaction, button):
        player = self.cog.player(interaction.guild)
        if player:
            player.queue.shuffle()
            await self.cog.save_state(interaction.guild.id)
        await interaction.response.defer()

    @discord.ui.button(label="Favorite", style=discord.ButtonStyle.secondary, custom_id="phantom:favorite")
    async def favorite(self, interaction, button):
        player = self.cog.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        add_favorite(interaction.user.id, interaction.guild.id, player.current)
        await interaction.response.send_message("Added to your favorites.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="phantom:stop")
    async def stop(self, interaction, button):
        player = self.cog.player(interaction.guild)
        await interaction.response.defer()
        if player:
            player.queue.clear()
            await player.stop()
        clear_queue_state(interaction.guild.id)
        state = self.cog.state(interaction.guild.id)
        if state.ticker and not state.ticker.done():
            state.ticker.cancel()
        if state.message:
            try:
                await state.message.delete()
            except discord.HTTPException:
                pass
            state.message = None
