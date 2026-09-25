import discord
from discord.ext import commands
import wavelink
from database import get_settings,set_setting,save_playlist,delete_playlist,list_playlists,get_playlist

class AdvancedMusic(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    def music(self,guild):
        return self.bot.get_cog("Music")

    def player(self,guild):
        m=self.music(guild)
        return m.player(guild) if m else None

    @commands.hybrid_command(name="previous",description="Play the previous track.")
    async def previous(self,i):
        p=self.player(i.guild)
        history=list(p.queue.history) if p else []
        if not p or not history:
            return await i.response.send_message("No previous track.",ephemeral=True)
        t=history[-1]
        await p.play(t)
        await i.response.send_message(f"Playing previous: **{t.title}**.",ephemeral=True)

    @commands.hybrid_command(name="seek",description="Seek to a position in seconds.")
    async def seek(self,i,seconds:int):
        p=self.player(i.guild)
        if not p or not p.current:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        await p.seek(max(0,seconds)*1000)
        await i.response.send_message("Position updated.",ephemeral=True)

    @commands.hybrid_command(name="replay",description="Restart the current track.")
    async def replay(self,i):
        p=self.player(i.guild)
        if not p or not p.current:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        await p.seek(0)
        await i.response.send_message("Restarted.",ephemeral=True)

    @commands.hybrid_command(name="repeat",description="Set repeat mode: off, song or queue.")
    async def repeat(self,i,mode:str):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        modes={"off":wavelink.QueueMode.normal,"song":wavelink.QueueMode.loop,"queue":wavelink.QueueMode.loop_all}
        mode=mode.lower()
        if mode not in modes:
            return await i.response.send_message("Use off, song or queue.",ephemeral=True)
        p.queue.mode=modes[mode]
        await i.response.send_message(f"Repeat: **{mode}**.",ephemeral=True)

    @commands.hybrid_command(name="remove",description="Remove a queue position.")
    async def remove(self,i,index:int):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        items=list(p.queue)
        if not 1<=index<=len(items):
            return await i.response.send_message("Invalid queue position.",ephemeral=True)
        p.queue.remove(items[index-1])
        await i.response.send_message("Removed.",ephemeral=True)

    @commands.hybrid_command(name="move",description="Move a queue item.")
    async def move(self,i,old:int,new:int):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        items=list(p.queue)
        if not 1<=old<=len(items) or not 1<=new<=len(items):
            return await i.response.send_message("Invalid queue position.",ephemeral=True)
        track=items[old-1]
        p.queue.remove(track)
        p.queue.put_at(new-1,track)
        await i.response.send_message("Moved.",ephemeral=True)

    @commands.hybrid_command(name="jump",description="Jump to a queue position.")
    async def jump(self,i,index:int):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        items=list(p.queue)
        if not 1<=index<=len(items):
            return await i.response.send_message("Invalid queue position.",ephemeral=True)
        target=items[index-1]
        p.queue.remove(target)
        await p.play(target)
        await i.response.send_message(f"Playing **{target.title}**.",ephemeral=True)

    @commands.hybrid_command(name="filter",description="Apply off, nightcore, bassboost, 8d or karaoke.")
    async def filter(self,i,name:str):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        name=name.lower()
        if name=="off":
            await p.set_filters()
        else:
            f=wavelink.Filters()
            if name=="nightcore":
                f.timescale.set(speed=1.25,pitch=1.15)
            elif name=="8d":
                f.rotation.set(rotation_hz=0.2)
            elif name=="bassboost":
                f.equalizer.set(bands=[(0,0.25),(1,0.20),(2,0.15),(3,0.10)])
            elif name=="karaoke":
                f.karaoke.set(level=1.0)
            else:
                return await i.response.send_message("Use off, nightcore, bassboost, 8d or karaoke.",ephemeral=True)
            await p.set_filters(f)
        await i.response.send_message(f"Filter: **{name}**.",ephemeral=True)

    @commands.hybrid_command(name="autoplay",description="Toggle automatic recommendations.")
    async def autoplay(self,i,enabled:bool):
        set_setting(i.guild.id,"autoplay",int(enabled))
        p=self.player(i.guild)
        if p:
            p.autoplay=wavelink.AutoPlayMode.enabled if enabled else wavelink.AutoPlayMode.disabled
        await i.response.send_message(f"Autoplay: **{'on' if enabled else 'off'}**.",ephemeral=True)

    @commands.hybrid_command(name="247",description="Toggle 24/7 voice mode.")
    async def always_on(self,i,enabled:bool):
        if not i.user.guild_permissions.manage_guild:
            return await i.response.send_message("Manage Server permission required.",ephemeral=True)
        set_setting(i.guild.id,"stay_24_7",int(enabled))
        await i.response.send_message(f"24/7: **{'on' if enabled else 'off'}**.",ephemeral=True)

    @commands.hybrid_command(name="playlist_save",description="Save the current queue as a personal playlist.")
    async def playlist_save(self,i,name:str):
        p=self.player(i.guild)
        if not p:
            return await i.response.send_message("Nothing is playing.",ephemeral=True)
        tracks=([p.current] if p.current else [])+list(p.queue)
        save_playlist(i.user.id,i.guild.id,name[:40],tracks)
        await i.response.send_message(f"Saved playlist **{name[:40]}**.",ephemeral=True)

    @commands.hybrid_command(name="playlist_load",description="Load a personal playlist.")
    async def playlist_load(self,i,name:str):
        rows=get_playlist(i.user.id,i.guild.id,name)
        if not rows:
            return await i.response.send_message("Playlist not found.",ephemeral=True)
        m=self.music(i.guild)
        await i.response.defer(ephemeral=True)
        p=await m.ensure(i)
        loaded=0
        for title,author,uri,artwork,duration,track_id in rows:
            try:
                result=await wavelink.Playable.search(uri or title)
                if result and not isinstance(result,wavelink.Playlist):
                    await p.queue.put_wait(result[0])
                    loaded+=1
            except Exception:
                continue
        if not p.playing and p.queue:
            await p.play(p.queue.get(),volume=get_settings(i.guild.id)[0])
        await i.followup.send(f"Loaded **{loaded}** tracks.",ephemeral=True)

    @commands.hybrid_command(name="playlists",description="List personal playlists.")
    async def playlists(self,i):
        names=list_playlists(i.user.id,i.guild.id)
        await i.response.send_message("\n".join(names) if names else "No playlists.",ephemeral=True)

    @commands.hybrid_command(name="playlist_delete",description="Delete a personal playlist.")
    async def playlist_delete(self,i,name:str):
        delete_playlist(i.user.id,i.guild.id,name)
        await i.response.send_message("Playlist deleted.",ephemeral=True)

    @commands.hybrid_command(name="history",description="Show recent playback history.")
    async def history(self,i):
        p=self.player(i.guild)
        history=list(p.queue.history) if p else []
        if not history:
            return await i.response.send_message("No history yet.",ephemeral=True)
        await i.response.send_message("\n".join(f"{n:02}. {t.title} — {t.author}" for n,t in enumerate(history[-20:][::-1],1)),ephemeral=True)

    @commands.hybrid_command(name="djrole",description="Set the DJ role.")
    @commands.has_guild_permissions(manage_guild=True)
    async def djrole(self,i,role:discord.Role):
        set_setting(i.guild.id,"dj_role_id",role.id)
        await i.response.send_message(f"DJ role set to **{role.name}**.",ephemeral=True)
