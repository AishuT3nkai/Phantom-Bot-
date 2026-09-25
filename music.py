import asyncio
import discord
from discord.ext import commands
import wavelink
from database import add_favorite,remove_favorite,get_favorites,get_settings
from card import render_card

class State:
    def __init__(self):
        self.message=None
        self.channel=None
        self.requester="Unknown"
        self.task=None
        self.lock=asyncio.Lock()

class Music(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.states={}

    def state(self,gid): return self.states.setdefault(gid,State())
    def player(self,guild): return guild.voice_client if isinstance(guild.voice_client,wavelink.Player) else None

    async def ensure(self,interaction):
        if not interaction.guild: raise RuntimeError("This command can only be used in a server.")
        if not interaction.user.voice: raise RuntimeError("Join a voice channel first.")
        p=self.player(interaction.guild)
        if p and p.channel != interaction.user.voice.channel:
            raise RuntimeError("Phantom is already in another voice channel.")
        if not p: p=await interaction.user.voice.channel.connect(cls=wavelink.Player)
        return p

    async def card(self,guild):
        p=self.player(guild); st=self.state(guild.id)
        if not p or not p.current or not st.channel: return
        async with st.lock:
            if st.message:
                try: await st.message.delete()
                except discord.HTTPException: pass
            img=await render_card(p.current,p.position,st.requester,p.paused)
            st.message=await st.channel.send(file=discord.File(img,"phantom-music.jpg"),view=Controls(self))

    async def ticker(self,gid):
        while True:
            await asyncio.sleep(60)
            guild=self.bot.get_guild(gid)
            if not guild or not self.player(guild) or not self.player(guild).current: return
            await self.card(guild)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self,payload):
        p=payload.player
        if not p or not p.guild: return
        st=self.state(p.guild.id)
        st.requester=getattr(p.current,"phantom_requester",st.requester)
        await self.card(p.guild)
        if st.task and not st.task.done(): st.task.cancel()
        st.task=asyncio.create_task(self.ticker(p.guild.id))

    @commands.hybrid_command(name="play",description="Play a song or playlist.")
    async def play(self,interaction,*,query:str):
        try: p=await self.ensure(interaction)
        except RuntimeError as e:
            await interaction.response.send_message(str(e),ephemeral=True); return
        tracks=await wavelink.Playable.search(query)
        if not tracks:
            await interaction.response.send_message("No tracks found.",ephemeral=True); return
        st=self.state(interaction.guild.id); st.channel=interaction.channel; st.requester=interaction.user.display_name
        if isinstance(tracks,wavelink.Playlist):
            for t in tracks: t.phantom_requester=st.requester
            await p.queue.put_wait(tracks)
            text=f"Added **{len(tracks)}** tracks from **{tracks.name}**."
        else:
            t=tracks[0]; t.phantom_requester=st.requester; await p.queue.put_wait(t)
            text=f"Added **{t.title}** — **{t.author}**."
        if not p.playing:
            await p.play(p.queue.get(),volume=get_settings(interaction.guild.id)[0])
        await interaction.response.send_message(text,ephemeral=True)

    @commands.hybrid_command(name="pause",description="Pause playback.")
    async def pause(self,interaction):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        await p.pause(True); await self.card(interaction.guild); await interaction.response.send_message("Paused.",ephemeral=True)

    @commands.hybrid_command(name="resume",description="Resume playback.")
    async def resume(self,interaction):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        await p.pause(False); await self.card(interaction.guild); await interaction.response.send_message("Resumed.",ephemeral=True)

    @commands.hybrid_command(name="skip",description="Skip the current song.")
    async def skip(self,interaction):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        await p.skip(force=True); await interaction.response.send_message("Skipped.",ephemeral=True)

    @commands.hybrid_command(name="stop",description="Stop and clear the queue.")
    async def stop(self,interaction):
        p=self.player(interaction.guild); st=self.state(interaction.guild.id)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        p.queue.clear(); await p.stop()
        if st.message:
            try: await st.message.delete()
            except discord.HTTPException: pass
            st.message=None
        await interaction.response.send_message("Stopped and cleared.",ephemeral=True)

    @commands.hybrid_command(name="queue",description="Show the queue.")
    async def queue(self,interaction):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        lines=[f"**Now:** {p.current.title} — {p.current.author}"] if p.current else []
        lines += [f"`{i:02}` {t.title} — {t.author}" for i,t in enumerate(list(p.queue)[:20],1)]
        await interaction.response.send_message("\n".join(lines) or "Queue is empty.",ephemeral=True)

    @commands.hybrid_command(name="shuffle",description="Shuffle the queue.")
    async def shuffle(self,interaction):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        p.queue.shuffle(); await interaction.response.send_message("Queue shuffled.",ephemeral=True)

    @commands.hybrid_command(name="volume",description="Set volume from 1 to 100.")
    async def volume(self,interaction,value:int):
        p=self.player(interaction.guild)
        if not p: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        value=max(1,min(100,value)); await p.set_volume(value); await interaction.response.send_message(f"Volume: **{value}%**",ephemeral=True)

    @commands.hybrid_command(name="leave",description="Leave the voice channel.")
    async def leave(self,interaction):
        p=self.player(interaction.guild)
        if p: await p.disconnect()
        await interaction.response.send_message("Disconnected.",ephemeral=True)

    @commands.hybrid_command(name="favorite",description="Favorite the current song.")
    async def favorite(self,interaction):
        p=self.player(interaction.guild)
        if not p or not p.current: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        add_favorite(interaction.user.id,interaction.guild.id,p.current)
        await interaction.response.send_message("Added to your favorites.",ephemeral=True)

    @commands.hybrid_command(name="unfavorite",description="Remove the current song from your favorites.")
    async def unfavorite(self,interaction):
        p=self.player(interaction.guild)
        if not p or not p.current: await interaction.response.send_message("Nothing is playing.",ephemeral=True); return
        remove_favorite(interaction.user.id,interaction.guild.id,p.current.identifier)
        await interaction.response.send_message("Removed.",ephemeral=True)

    @commands.hybrid_command(name="favorites",description="View a user's favorites.")
    async def favorites(self,interaction,member:discord.Member=None):
        member=member or interaction.user
        rows=get_favorites(member.id,interaction.guild.id)
        if not rows: await interaction.response.send_message(f"{member.display_name} has no favorites.",ephemeral=True); return
        lines=[f"**{member.display_name}'s Favorites**"]+[f"{i:02}. {r[0]} — {r[1]}" for i,r in enumerate(rows[:25],1)]
        await interaction.response.send_message("\n".join(lines))

class Controls(discord.ui.View):
    def __init__(self,cog): super().__init__(timeout=None); self.cog=cog
    async def p(self,i): return self.cog.player(i.guild)
    @discord.ui.button(label="Pause",style=discord.ButtonStyle.primary)
    async def pause(self,i,b):
        p=await self.p(i)
        if p: await p.pause(not p.paused)
        await i.response.defer()
    @discord.ui.button(label="Skip",style=discord.ButtonStyle.secondary)
    async def skip(self,i,b):
        p=await self.p(i)
        if p: await p.skip(force=True)
        await i.response.defer()
    @discord.ui.button(label="Shuffle",style=discord.ButtonStyle.secondary)
    async def shuffle(self,i,b):
        p=await self.p(i)
        if p: p.queue.shuffle()
        await i.response.defer()
    @discord.ui.button(label="Stop",style=discord.ButtonStyle.danger)
    async def stop(self,i,b):
        p=await self.p(i)
        if p: p.queue.clear(); await p.stop()
        await i.response.defer()
