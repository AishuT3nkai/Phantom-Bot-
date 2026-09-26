import asyncio
import logging
import sqlite3
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

log = logging.getLogger('aishu.security')
OWNER_ID = 1534184389838114857
HONEYPOT_NAME = '〔⛔〕┇Ignore me'
LOG_CHANNEL_NAME = 'aishu-logs'
QUARANTINE_ROLE_NAME = 'Aishu Quarantine'
DEFAULTS = {'spam_enabled': True, 'spam_messages': 5, 'spam_window': 5, 'duplicate_messages': 3, 'duplicate_window': 10, 'timeout_minutes': 60, 'joinraid_enabled': True, 'joinraid_count': 8, 'joinraid_window': 60, 'joinraid_action': 'timeout', 'joinraid_timeout': 60, 'honeypot_enabled': False, 'antinuke_enabled': True, 'antinuke_limit': 3, 'lockdown': False}

class Store:
    def __init__(self):
        self.db = sqlite3.connect('aishu_security.db')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
        self.db.commit()
    def get(self, guild_id):
        import json
        row = self.db.execute('SELECT data FROM settings WHERE guild_id=?', (guild_id,)).fetchone()
        data = dict(DEFAULTS)
        if row: data.update(json.loads(row[0]))
        return data
    def set(self, guild_id, **values):
        import json
        data = self.get(guild_id); data.update(values)
        self.db.execute('INSERT OR REPLACE INTO settings(guild_id,data) VALUES(?,?)', (guild_id, json.dumps(data)))
        self.db.commit()

class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot; self.store = Store()
        self.message_times = defaultdict(deque); self.duplicate_times = defaultdict(deque)
        self.joins = defaultdict(deque); self.actions = defaultdict(deque)

    def cfg(self, guild_id): return self.store.get(guild_id)
    def exempt(self, member):
        if member.id == OWNER_ID or member.id == member.guild.owner_id: return True
        p = member.guild_permissions
        return p.administrator or p.manage_guild or p.manage_channels or p.moderate_members

    async def notify_owner(self, guild, title, description):
        try:
            user = self.bot.get_user(OWNER_ID) or await self.bot.fetch_user(OWNER_ID)
            embed = discord.Embed(title=title, description=description); embed.set_footer(text='Powered by Aishu')
            await user.send(embed=embed)
        except (discord.HTTPException, discord.Forbidden): log.warning('Could not DM owner %s', OWNER_ID)

    async def log_event(self, guild, title, description):
        channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if channel:
            try: await channel.send(embed=discord.Embed(title=title, description=description))
            except discord.HTTPException: pass

    async def punish(self, member, reason, minutes=60):
        if not isinstance(member, discord.Member) or self.exempt(member): return False
        me = member.guild.me
        if not me or not me.guild_permissions.moderate_members or member.top_role >= me.top_role: return False
        try:
            await member.timeout(timedelta(minutes=minutes), reason=reason)
            await self.notify_owner(member.guild, 'Security action', f'User: {member} ({member.id})\nServer: {member.guild.name} ({member.guild.id})\nAction: timeout {minutes} minutes\nReason: {reason}')
            await self.log_event(member.guild, 'Timeout', f'{member} ({member.id})\n{reason}')
            return True
        except discord.HTTPException: log.exception('Timeout failed for %s', member.id); return False

    async def kick_member(self, member, reason):
        if self.exempt(member): return False
        me=member.guild.me
        if not me or not me.guild_permissions.kick_members or member.top_role >= me.top_role: return False
        try: await member.kick(reason=reason); await self.log_event(member.guild,'Kick',f'{member} ({member.id})\n{reason}'); return True
        except discord.HTTPException: return False

    async def ban_member(self, member, reason):
        if self.exempt(member): return False
        me=member.guild.me
        if not me or not me.guild_permissions.ban_members or member.top_role >= me.top_role: return False
        try: await member.ban(reason=reason, delete_message_seconds=86400); await self.log_event(member.guild,'Ban',f'{member} ({member.id})\n{reason}'); return True
        except discord.HTTPException: return False

    def is_spam(self, message):
        cfg=self.cfg(message.guild.id); key=(message.guild.id,message.author.id); now=time.monotonic()
        t=self.message_times[key]
        while t and now-t[0]>cfg['spam_window']: t.popleft()
        t.append(now)
        if len(t)>=cfg['spam_messages']: return True
        content=message.content.strip().casefold()
        if not content: return False
        d=self.duplicate_times[key]
        while d and now-d[0][0]>cfg['duplicate_window']: d.popleft()
        d.append((now,content))
        return sum(v==content for _,v in d)>=cfg['duplicate_messages']

    async def ensure_honeypot(self,guild):
        c=discord.utils.get(guild.text_channels,name=HONEYPOT_NAME)
        if c: return c
        c=await guild.create_text_channel(HONEYPOT_NAME,topic='Aishu anti-raid honeypot. Do not send messages here.',reason='Aishu anti-raid honeypot')
        e=discord.Embed(title='DO NOT SEND MESSAGES IN THIS CHANNEL',description='It is used to catch spam bots. Any messages sent here will result in a softban.')
        e.set_footer(text='Powered by Aishu'); await c.send(embed=e); return c

    async def quarantine_role(self,guild):
        r=discord.utils.get(guild.roles,name=QUARANTINE_ROLE_NAME)
        if not r: r=await guild.create_role(name=QUARANTINE_ROLE_NAME,color=discord.Color.dark_grey(),reason='Aishu security quarantine')
        return r

    @commands.hybrid_command(name='active',description='Activate Aishu anti-raid protection.')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def active(self,ctx):
        self.store.set(ctx.guild.id,spam_enabled=True,joinraid_enabled=True,antinuke_enabled=True,honeypot_enabled=True)
        try:
            c=await self.ensure_honeypot(ctx.guild); await ctx.send(f'Protection activated. Honeypot: {c.mention}',ephemeral=True)
        except discord.HTTPException: await ctx.send('Protection enabled, but I could not create the honeypot.',ephemeral=True)

    @commands.hybrid_command(name='deactivate',description='Disable Aishu anti-raid protection.')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def deactivate(self,ctx):
        self.store.set(ctx.guild.id,spam_enabled=False,joinraid_enabled=False,antinuke_enabled=False,honeypot_enabled=False)
        await ctx.send('Anti-raid protection disabled.',ephemeral=True)

    @commands.hybrid_command(name='timeout',description='Timeout a member.')
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self,ctx,member:discord.Member,minutes:int=60,*,reason:str='Moderator action'):
        ok=await self.punish(member,reason,max(1,min(minutes,40320))); await ctx.send('Timeout applied.' if ok else 'I could not timeout that member.',ephemeral=True)

    @commands.hybrid_command(name='kick',description='Kick a member.')
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(self,ctx,member:discord.Member,*,reason:str='Moderator action'):
        ok=await self.kick_member(member,reason); await ctx.send('Member kicked.' if ok else 'I could not kick that member.',ephemeral=True)

    @commands.hybrid_command(name='ban',description='Ban a member.')
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self,ctx,member:discord.Member,*,reason:str='Moderator action'):
        ok=await self.ban_member(member,reason); await ctx.send('Member banned.' if ok else 'I could not ban that member.',ephemeral=True)

    @commands.hybrid_command(name='quarantine',description='Quarantine a member.')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def quarantine(self,ctx,member:discord.Member,*,reason:str='Security quarantine'):
        if self.exempt(member): return await ctx.send('That member is protected.',ephemeral=True)
        r=await self.quarantine_role(ctx.guild); await member.add_roles(r,reason=reason); await self.log_event(ctx.guild,'Quarantine',f'{member} ({member.id})\n{reason}'); await ctx.send('Member quarantined.',ephemeral=True)

    @commands.hybrid_command(name='unquarantine',description='Remove quarantine from a member.')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def unquarantine(self,ctx,member:discord.Member):
        r=discord.utils.get(ctx.guild.roles,name=QUARANTINE_ROLE_NAME)
        if r and r in member.roles: await member.remove_roles(r,reason='Aishu quarantine removal')
        await ctx.send('Quarantine removed.',ephemeral=True)

    @commands.hybrid_command(name='lockdown',description='Lock text channels.')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self,ctx):
        await ctx.defer(ephemeral=True); n=0
        for c in ctx.guild.text_channels:
            o=c.overwrites_for(ctx.guild.default_role); o.send_messages=False
            try: await c.set_permissions(ctx.guild.default_role,overwrite=o,reason='Aishu lockdown'); n+=1
            except discord.HTTPException: pass
        self.store.set(ctx.guild.id,lockdown=True); await ctx.followup.send(f'Lockdown enabled on {n} text channels.',ephemeral=True)

    @commands.hybrid_command(name='unlock',description='Remove lockdown.')
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self,ctx):
        await ctx.defer(ephemeral=True); n=0
        for c in ctx.guild.text_channels:
            o=c.overwrites_for(ctx.guild.default_role); o.send_messages=None
            try: await c.set_permissions(ctx.guild.default_role,overwrite=o,reason='Aishu unlock'); n+=1
            except discord.HTTPException: pass
        self.store.set(ctx.guild.id,lockdown=False); await ctx.followup.send(f'Lockdown removed from {n} text channels.',ephemeral=True)

    @commands.hybrid_command(name='settings',description='Show security settings.')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def settings(self,ctx):
        c=self.cfg(ctx.guild.id); e=discord.Embed(title='Aishu Security Settings')
        e.add_field(name='Spam',value=f"{c['spam_enabled']} • {c['spam_messages']} messages / {c['spam_window']}s")
        e.add_field(name='Duplicate',value=f"{c['duplicate_messages']} / {c['duplicate_window']}s")
        e.add_field(name='Timeout',value=f"{c['timeout_minutes']} minutes")
        e.add_field(name='Join Raid',value=f"{c['joinraid_enabled']} • {c['joinraid_count']} joins / {c['joinraid_window']}s")
        e.add_field(name='Anti-Nuke',value=f"{c['antinuke_enabled']} • {c['antinuke_limit']} actions")
        e.add_field(name='Honeypot',value=str(c['honeypot_enabled'])); await ctx.send(embed=e,ephemeral=True)

    @commands.hybrid_command(name='clear',description='Delete recent messages.')
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clear(self,ctx,amount:int=10):
        amount=max(1,min(amount,100)); await ctx.defer(ephemeral=True); deleted=await ctx.channel.purge(limit=amount); await ctx.followup.send(f'Deleted {len(deleted)} messages.',ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self,message):
        if message.author.bot or not message.guild or self.exempt(message.author): return
        c=self.cfg(message.guild.id)
        if c['honeypot_enabled'] and message.channel.name==HONEYPOT_NAME:
            if await self.ban_member(message.author,'Aishu honeypot triggered'):
                try: await message.guild.unban(message.author,reason='Aishu honeypot softban')
                except discord.HTTPException: pass
            return
        if self.is_spam(message): await self.punish(message.author,'Aishu anti-spam: message spam detected',c['timeout_minutes'])

    @commands.Cog.listener()
    async def on_member_join(self,member):
        c=self.cfg(member.guild.id)
        if not c['joinraid_enabled']: return
        now=time.monotonic(); j=self.joins[member.guild.id]
        while j and now-j[0]>c['joinraid_window']: j.popleft()
        j.append(now)
        if len(j)>=c['joinraid_count'] and not self.exempt(member):
            if c['joinraid_action']=='ban': await self.ban_member(member,'Aishu JoinRaid triggered')
            elif c['joinraid_action']=='kick': await self.kick_member(member,'Aishu JoinRaid triggered')
            else: await self.punish(member,'Aishu JoinRaid triggered',c['joinraid_timeout'])

    async def _audit_actor(self,guild,action):
        try:
            async for e in guild.audit_logs(limit=1,action=action):
                if time.time()-e.created_at.timestamp()<15: return e.user
        except discord.HTTPException: pass
        return None

    async def _antinuke(self,guild,action,label):
        c=self.cfg(guild.id)
        if not c['antinuke_enabled']: return
        actor=await self._audit_actor(guild,action)
        if not isinstance(actor, discord.abc.User): return
        actor = guild.get_member(actor.id)
        if not actor or self.exempt(actor): return
        key=(guild.id,actor.id); now=time.monotonic(); q=self.actions[key]
        while q and now-q[0]>60: q.popleft()
        q.append(now)
        if len(q)>=c['antinuke_limit']: await self.punish(actor,f'Aishu Anti-Nuke: {label}',60)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self,c): await self._antinuke(c.guild,discord.AuditLogAction.channel_delete,'mass channel deletion')
    @commands.Cog.listener()
    async def on_guild_role_delete(self,r): await self._antinuke(r.guild,discord.AuditLogAction.role_delete,'mass role deletion')
    @commands.Cog.listener()
    async def on_guild_channel_create(self,c): await self._antinuke(c.guild,discord.AuditLogAction.channel_create,'mass channel creation')
    @commands.Cog.listener()
    async def on_guild_role_create(self,r): await self._antinuke(r.guild,discord.AuditLogAction.role_create,'mass role creation')

async def setup(bot): await bot.add_cog(Security(bot))