import io
import json

import discord
from discord.ext import commands
import wavelink

from database import (
    delete_playlist, export_playlist, get_history, get_playlist,
    get_settings, import_playlist, list_playlists, save_playlist,
    set_setting
)

class AdvancedMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def music(self):
        return self.bot.get_cog("Music")

    def player(self, guild):
        cog = self.music()
        return cog.player(guild) if cog else None

    async def control(self, interaction):
        cog = self.music()
        return bool(cog and await cog.can_control(interaction))

    @commands.hybrid_command(name="nowplaying", description="Show the current track and playback position.")
    async def nowplaying(self, interaction):
        player = self.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        position = max(0, int(player.position or 0)) // 1000
        total = max(0, int(player.current.length or 0)) // 1000
        state = "paused" if player.paused else "playing"
        await interaction.response.send_message(f"Now playing: {player.current.title} — {player.current.author}\\n{position // 60:02d}:{position % 60:02d} / {total // 60:02d}:{total % 60:02d} · {state}", ephemeral=True)

    @commands.hybrid_command(name="previous", description="Play the previous track.")
    async def previous(self, interaction):
        if not await self.control(interaction):
            return
        cog = self.music()
        track = await cog.previous_track(interaction.guild)
        if not track:
            return await interaction.response.send_message("No previous track.", ephemeral=True)
        player = cog.player(interaction.guild)
        await player.play(track, volume=get_settings(interaction.guild.id)[0])
        await cog.save_state(interaction.guild.id)
        await interaction.response.send_message(f"Playing previous: {track.title}.", ephemeral=True)

    @commands.hybrid_command(name="seek", description="Seek to a position in seconds.")
    async def seek(self, interaction, seconds: int):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        target = max(0, min(seconds * 1000, max(0, player.current.length - 1000)))
        await player.seek(target)
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message("Position updated.", ephemeral=True)

    @commands.hybrid_command(name="replay", description="Restart the current track.")
    async def replay(self, interaction):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await player.seek(0)
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message("Restarted.", ephemeral=True)

    @commands.hybrid_command(name="repeat", description="Set repeat mode: off, song or queue.")
    async def repeat(self, interaction, mode: str):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        modes = {
            "off": wavelink.QueueMode.normal,
            "song": wavelink.QueueMode.loop,
            "queue": wavelink.QueueMode.loop_all,
        }
        mode = mode.lower()
        if mode not in modes:
            return await interaction.response.send_message("Use off, song or queue.", ephemeral=True)
        player.queue.mode = modes[mode]
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message(f"Repeat: {mode}.", ephemeral=True)

    @commands.hybrid_command(name="remove", description="Remove a queue position.")
    async def remove(self, interaction, index: int):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        items = list(player.queue)
        if not 1 <= index <= len(items):
            return await interaction.response.send_message("Invalid queue position.", ephemeral=True)
        player.queue.remove(items[index - 1])
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message("Removed.", ephemeral=True)

    @commands.hybrid_command(name="move", description="Move a queue item.")
    async def move(self, interaction, old: int, new: int):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        items = list(player.queue)
        if not 1 <= old <= len(items) or not 1 <= new <= len(items):
            return await interaction.response.send_message("Invalid queue position.", ephemeral=True)
        track = items[old - 1]
        player.queue.remove(track)
        player.queue.put_at(new - 1, track)
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message("Moved.", ephemeral=True)

    @commands.hybrid_command(name="jump", description="Jump to a queue position.")
    async def jump(self, interaction, index: int):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        items = list(player.queue)
        if not 1 <= index <= len(items):
            return await interaction.response.send_message("Invalid queue position.", ephemeral=True)
        track = items[index - 1]
        player.queue.remove(track)
        await player.play(track, volume=get_settings(interaction.guild.id)[0])
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message(f"Playing {track.title}.", ephemeral=True)

    @commands.hybrid_command(name="clear", description="Clear the waiting queue.")
    async def clear(self, interaction):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        player.queue.clear()
        await self.music().save_state(interaction.guild.id)
        await interaction.response.send_message("Queue cleared.", ephemeral=True)

    @commands.hybrid_command(name="filter", description="Apply off, nightcore, bassboost, 8d or karaoke.")
    async def filter(self, interaction, name: str):
        if not await self.control(interaction):
            return
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        name = name.lower()
        if name == "off":
            await player.set_filters()
        else:
            filters = wavelink.Filters()
            if name == "nightcore":
                filters.timescale.set(speed=1.25, pitch=1.15)
            elif name == "8d":
                filters.rotation.set(rotation_hz=0.2)
            elif name == "bassboost":
                filters.equalizer.set(bands=[(0, 0.25), (1, 0.20), (2, 0.15), (3, 0.10)])
            elif name == "karaoke":
                filters.karaoke.set(level=1.0)
            else:
                return await interaction.response.send_message(
                    "Use off, nightcore, bassboost, 8d or karaoke.", ephemeral=True
                )
            await player.set_filters(filters)
        await interaction.response.send_message(f"Filter: {name}.", ephemeral=True)

    @commands.hybrid_command(name="autoplay", description="Toggle automatic recommendations.")
    async def autoplay(self, interaction, enabled: bool):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
        set_setting(interaction.guild.id, "autoplay", int(enabled))
        player = self.player(interaction.guild)
        if player:
            player.autoplay = wavelink.AutoPlayMode.enabled if enabled else wavelink.AutoPlayMode.disabled
        await interaction.response.send_message(f"Autoplay: {'on' if enabled else 'off'}.", ephemeral=True)

    @commands.hybrid_command(name="247", description="Toggle 24/7 voice recovery.")
    async def always_on(self, interaction, enabled: bool):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
        set_setting(interaction.guild.id, "stay_24_7", int(enabled))
        await interaction.response.send_message(f"24/7: {'on' if enabled else 'off'}.", ephemeral=True)

    @commands.hybrid_command(name="restore", description="Restore the saved queue after a restart.")
    async def restore(self, interaction):
        if not await self.control(interaction):
            return
        cog = self.music()
        await cog.restore_saved(interaction.guild.id)
        if self.player(interaction.guild):
            await interaction.response.send_message("Saved music state restored.", ephemeral=True)
        else:
            await interaction.response.send_message("No restorable saved state was found.", ephemeral=True)

    @commands.hybrid_command(name="playlist_save", description="Save the current queue as a personal playlist.")
    async def playlist_save(self, interaction, name: str):
        player = self.player(interaction.guild)
        if not player:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        tracks = ([player.current] if player.current else []) + list(player.queue)
        save_playlist(interaction.user.id, interaction.guild.id, name, tracks)
        await interaction.response.send_message(f"Saved playlist {name[:40]}.", ephemeral=True)

    @commands.hybrid_command(name="playlist_load", description="Load a personal playlist.")
    async def playlist_load(self, interaction, name: str):
        names = list_playlists(interaction.user.id, interaction.guild.id)
        if name not in names:
            return await interaction.response.send_message("Playlist not found.", ephemeral=True)
        cog = self.music()
        await interaction.response.defer(ephemeral=True)
        player = await cog.ensure(interaction)
        loaded = 0
        for title, author, uri, artwork, duration, track_id in get_playlist(
            interaction.user.id, interaction.guild.id, name
        ):
            track = await cog.resolve_track(uri or title)
            if track:
                track.phantom_requester = interaction.user.display_name
                track.phantom_requester_id = interaction.user.id
                player.queue.put(track)
                loaded += 1
        if not player.playing and player.queue:
            await player.play(player.queue.get(), volume=get_settings(interaction.guild.id)[0])
        await cog.save_state(interaction.guild.id)
        await interaction.followup.send(f"Loaded {loaded} tracks.", ephemeral=True)

    @commands.hybrid_command(name="playlists", description="List your personal playlists.")
    async def playlists(self, interaction):
        names = list_playlists(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message("\\n".join(names) if names else "No playlists.", ephemeral=True)

    @commands.hybrid_command(name="playlist_delete", description="Delete a personal playlist.")
    async def playlist_delete(self, interaction, name: str):
        delete_playlist(interaction.user.id, interaction.guild.id, name)
        await interaction.response.send_message("Playlist deleted.", ephemeral=True)

    @commands.hybrid_command(name="playlist_export", description="Export a personal playlist as JSON.")
    async def playlist_export(self, interaction, name: str):
        if name not in list_playlists(interaction.user.id, interaction.guild.id):
            return await interaction.response.send_message("Playlist not found.", ephemeral=True)
        payload = export_playlist(interaction.user.id, interaction.guild.id, name)
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        if len(raw) > 1024 * 1024:
            return await interaction.response.send_message("Playlist export is too large.", ephemeral=True)
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(raw), filename=f"{name[:32]}.json"),
            ephemeral=True,
        )

    @commands.hybrid_command(name="playlist_import", description="Import a playlist JSON file.")
    async def playlist_import(self, interaction, attachment: discord.Attachment):
        if not attachment.filename.lower().endswith(".json"):
            return await interaction.response.send_message("Attach a JSON playlist file.", ephemeral=True)
        if attachment.size and attachment.size > 1024 * 1024:
            return await interaction.response.send_message("The playlist file is too large.", ephemeral=True)
        try:
            payload = json.loads((await attachment.read()).decode("utf-8"))
            name, count = import_playlist(interaction.user.id, interaction.guild.id, payload)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return await interaction.response.send_message("Invalid playlist JSON.", ephemeral=True)
        await interaction.response.send_message(f"Imported {name} with {count} tracks.", ephemeral=True)

    @commands.hybrid_command(name="history", description="Show persistent playback history.")
    async def history(self, interaction):
        rows = get_history(interaction.guild.id, 20)
        if not rows:
            return await interaction.response.send_message("No history yet.", ephemeral=True)
        text = "\\n".join(f"{n:02}. {row[0]} — {row[1]}" for n, row in enumerate(rows, 1))
        await interaction.response.send_message(text, ephemeral=True)

    @commands.hybrid_command(name="djrole", description="Set or replace the DJ role.")
    @commands.has_guild_permissions(manage_guild=True)
    async def djrole(self, interaction, role: discord.Role):
        set_setting(interaction.guild.id, "dj_role_id", role.id)
        await interaction.response.send_message(f"DJ role set to {role.name}.", ephemeral=True)

    @commands.hybrid_command(name="djrole_clear", description="Disable the DJ role requirement.")
    @commands.has_guild_permissions(manage_guild=True)
    async def djrole_clear(self, interaction):
        set_setting(interaction.guild.id, "dj_role_id", None)
        await interaction.response.send_message("DJ role requirement disabled.", ephemeral=True)

    @commands.hybrid_command(name="maxqueue", description="Set the maximum waiting queue size.")
    @commands.has_guild_permissions(manage_guild=True)
    async def maxqueue(self, interaction, value: int):
        value = max(10, min(500, value))
        set_setting(interaction.guild.id, "max_queue", value)
        await interaction.response.send_message(f"Maximum queue: {value}.", ephemeral=True)
