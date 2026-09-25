import asyncio

import discord
from discord.ext import commands
import wavelink

from database import get_settings

SEARCH_PREFIXES = ("ytmsearch:", "ytsearch:", "scsearch:", "dzsearch:", "spsearch:", "amsearch:")

class SearchSelect(discord.ui.Select):
    def __init__(self, cog, tracks):
        self.cog = cog
        self.tracks = tracks
        options = []
        for index, (source, track) in enumerate(tracks[:25]):
            options.append(
                discord.SelectOption(
                    label=str(track.title)[:100],
                    description=f"{source} | {track.author[:70]} | {cog.time(track.length)}",
                    value=str(index)
                )
            )
        super().__init__(
            placeholder="Select a result",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        music = self.cog.bot.get_cog("Music")
        if not music:
            return await interaction.response.edit_message(content="Music system unavailable.", view=None)
        if not await music.can_control(interaction):
            return
        source, track = self.tracks[int(self.values[0])]
        try:
            player = await music.ensure(interaction)
            _, max_queue, _, autoplay, _ = get_settings(interaction.guild.id)
            if player.queue.count >= max_queue:
                return await interaction.response.edit_message(content="Queue is full.", view=None)
            music.tag(track, interaction)
            player.autoplay = wavelink.AutoPlayMode.enabled if autoplay else wavelink.AutoPlayMode.disabled
            player.queue.put(track)
            state = music.state(interaction.guild.id)
            state.channel = interaction.channel
            state.requester_id = interaction.user.id
            state.requester = interaction.user.display_name
            if not player.playing and player.queue:
                await player.play(player.queue.get(), volume=get_settings(interaction.guild.id)[0])
            await music.save_state(interaction.guild.id)
            await interaction.response.edit_message(
                content=f"Added {track.title} — {track.author} from {source}.",
                view=None
            )
        except Exception as exc:
            try:
                await interaction.response.edit_message(content=f"Music error: {exc}", view=None)
            except discord.HTTPException:
                pass

class SearchView(discord.ui.View):
    def __init__(self, cog, tracks):
        super().__init__(timeout=45)
        self.add_item(SearchSelect(cog, tracks))

class SearchMusic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def time(self, milliseconds):
        seconds = max(0, int(milliseconds or 0) // 1000)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    async def search_source(self, prefix, query):
        try:
            result = await wavelink.Playable.search(prefix + query)
        except Exception:
            return []
        if isinstance(result, wavelink.Playlist):
            return []
        return list(result)

    async def multi_search(self, query):
        results = await asyncio.gather(
            *(self.search_source(prefix, query) for prefix in SEARCH_PREFIXES),
            return_exceptions=True
        )
        output = []
        seen = set()
        for prefix, result in zip(SEARCH_PREFIXES, results):
            if isinstance(result, Exception):
                continue
            source = prefix.split(":", 1)[0].upper()
            for track in result:
                key = (
                    str(track.title).strip().lower(),
                    str(track.author).strip().lower(),
                    int(track.length or 0)
                )
                if key in seen:
                    continue
                seen.add(key)
                output.append((source, track))
                if len(output) >= 25:
                    return output
        return output

    @commands.hybrid_command(name="search", description="Search multiple music sources.")
    async def search(self, interaction, *, query: str):
        await interaction.response.defer(ephemeral=True)
        tracks = await self.multi_search(query)
        if not tracks:
            return await interaction.followup.send("No results found.", ephemeral=True)
        await interaction.followup.send(
            "Choose a result:",
            view=SearchView(self, tracks),
            ephemeral=True
        )
