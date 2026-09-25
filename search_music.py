import asyncio
import discord
from discord.ext import commands
import wavelink

PREFIXES=("ytmsearch:","ytsearch:","scsearch:","dzsearch:","spsearch:","amsearch:")

class SearchSelect(discord.ui.Select):
    def __init__(self,cog,tracks):
        self.cog=cog
        self.tracks=tracks
        super().__init__(
            placeholder="Select a source/result",
            min_values=1,max_values=1,
            options=[
                discord.SelectOption(
                    label=t.title[:100],
                    description=f"{t.author[:70]} • {cog.ms(t.length)}",
                    value=str(n)
                ) for n,t in enumerate(tracks[:10])
            ]
        )

    async def callback(self,interaction):
        t=self.tracks[int(self.values[0])]
        music=self.cog.bot.get_cog("Music")
        try:
            await music.enqueue(interaction,t)
            await interaction.response.edit_message(content=f"Added **{t.title}** — **{t.author}**.",view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"Music error: {e}",view=None)

class SearchView(discord.ui.View):
    def __init__(self,cog,tracks):
        super().__init__(timeout=45)
        self.add_item(SearchSelect(cog,tracks))

class SearchMusic(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    def ms(self,ms):
        s=max(0,int(ms or 0)//1000)
        return f"{s//60:02d}:{s%60:02d}"

    async def multi_search(self,query):
        results=await asyncio.gather(
            *(wavelink.Playable.search(prefix+query) for prefix in PREFIXES),
            return_exceptions=True
        )
        out=[]
        seen=set()
        for result in results:
            if isinstance(result,Exception) or isinstance(result,wavelink.Playlist):
                continue
            for track in result:
                key=(str(track.title).lower(),str(track.author).lower(),int(track.length))
                if key not in seen:
                    seen.add(key)
                    out.append(track)
        return out[:10]

    @commands.hybrid_command(name="search",description="Search multiple music sources.")
    async def search(self,interaction,*,query:str):
        await interaction.response.defer(ephemeral=True)
        tracks=await self.multi_search(query)
        if not tracks:
            return await interaction.followup.send("No results found.",ephemeral=True)
        await interaction.followup.send("Choose a result:",view=SearchView(self,tracks),ephemeral=True)
