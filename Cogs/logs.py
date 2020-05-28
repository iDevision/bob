import datetime
import time
import typing
import discord

from utils import btime, commands, objects


def setup(bot):
    bot.add_cog(logging(bot))


class logging(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.bucket = commands.CooldownMapping.from_cooldown(1,0.3,commands.BucketType.guild)
        self.states = bot.logging_states

    def is_enabled(self, guild):
        return self.bot.guild_module_states[guild.id]['modlogs'] and guild.id in self.bot.logging_states and self.bot.logging_states[guild.id] is not None

    def has_permission(self, guild):
        return guild.me.guild_permissions.view_audit_log

    async def get_audit_logs(self, guild, limit=100, user=None, action=None)->list:
        try:
            return await self.bot.get_guild(guild.id).audit_logs(limit=limit, user=user, action=action).flatten()
        except:
            return []

    def get_embed(self, color=0xFFFF00):
        emb = commands.Embed()
        emb.colour = color
        emb.timestamp = datetime.datetime.utcnow()
        return emb

    def get_state(self, guild)->objects.LoggingFlags:
        if guild.id not in self.states:
            return None

        if self.states[guild.id] is not None and not self.states[guild.id].channel:
            return None

        return self.states[guild.id]

    async def send_to_channel(self, state, content=None, embed=None):
        channel = self.bot.get_channel(state.channel)
        if channel is None:
            return

        try:
            await channel.send(content, embed=embed)
        except commands.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member, silence=False):
        if silence:
            return

        state = self.get_state(member.guild)
        if state is None or not state.member_join:
            return

        embed = self.get_embed(commands.Color.green())
        embed.title = "Member Joined"
        embed.description = f"<:memberjoin:684549887001624601> {member.mention} - {member}"
        embed.set_footer(text=f"id: {member.id}")

        if member.created_at > (datetime.datetime.utcnow() - datetime.timedelta(days=7)):
            embed.add_field(name="New User Alert", value=f"<:alert:498095663729344514> Account created {btime.human_timedelta(member.created_at)}")
            embed.colour = 0xdda453

        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        state = self.get_state(member.guild)
        if state is None or not state.member_leave:
            return

        embed = self.get_embed(commands.Color.red())
        embed.title = "User Left"
        embed.description = f"<:memberleave:432986578672156673> {member.mention}\nname: {member}\n"
        embed.set_footer(text=f"id: {member.id}")

        if not self.has_permission(member.guild):
            embed.description =  f"<:memberleave:432986578672156673> {member}\n(unable to resolve leave/kick. I can't see the audit logs!)"
            await self.send_to_channel(state, embed=embed)
            return

        klogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.kick)

        if klogs and (datetime.datetime.utcnow() - klogs[0].created_at).total_seconds() < 2:
            if not state.member_kick:
                return

            embed.add_field(name="Moderator", value=klogs[0].user.mention + f" - name: {klogs[0].user} (id: {klogs[0].user.id})")
            embed.title = "User Kicked"
            await self.send_to_channel(state, embed=embed)
            return

        blogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.ban)

        if blogs and (datetime.datetime.utcnow() - blogs[0].created_at).total_seconds() < 2:
            return

        # determined its a leave
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        state = self.get_state(after.guild)
        if state is None:
            return

        if not state.member_update:
            return

        if before.nick != after.nick:
            embed = self.get_embed(discord.Color.blurple())
            embed.title = "Nickname Changed"
            embed.description = f"<:memberupdate:684549878525067306> \n**Before:** {before.nick}\n**After:** {after.nick}"
            embed.set_footer(text=f"id: {after.id}")
            await self.send_to_channel(state, embed=embed)

        if before.roles != after.roles:
            pass # TODO

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: commands.RawMessageDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id)
        state = self.get_state(guild)
        if state is None or not state.message_delete:
            return

        if payload.message_id in self.bot.logging_ignore:
            self.bot.logging_ignore.remove(payload.message_id)
            await self.bot.pg.execute("DELETE FROM modlog_messages WHERE message_id = $1;", payload.message_id)
            return


        msg = await self.bot.pg.fetchrow("SELECT content, user_id FROM modlog_messages WHERE message_id = $1", payload.message_id)
        if not msg:
            return

        embed = self.get_embed(commands.Color.red())
        embed.title = "Message Deleted"
        embed.description = f"<:messagedelete:684549889182531604> <@{msg['user_id']}>\nin: <#{payload.channel_id}>\n"
        embed.add_field(name="Content", value=msg['content'])
        embed.set_footer(text=f"user id: {msg['user_id']}")

        if not self.has_permission(guild):
            embed.description += "(unable to determine who deleted the message. I can't see the audit logs)"
            await self.send_to_channel(state, embed=embed)
            return

        log = await self.get_audit_logs(guild, limit=1, action=commands.AuditLogAction.message_delete)
        if log and (datetime.datetime.utcnow() - log[0].created_at).total_seconds() < 2:
            embed.add_field(name="Deleted by", value=f"{log[0].user.mention} - {log[0].user} (id: {log[0].user.id})")

        await self.send_to_channel(state, embed=embed)
        await self.bot.pg.execute("DELETE FROM modlog_messages WHERE message_id = $1;", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: commands.RawBulkMessageDeleteEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)

        state = self.get_state(guild)
        if state is None or not state.message_delete:
            return

        amount = len(payload.message_ids)
        embed = self.get_embed(commands.Color.red())
        embed.title = "Messages Deleted"
        embed.description = f"<:messagedelete:684549889182531604>\n {amount} messages deleted"
        
        await self.send_to_channel(state, embed=embed)
        await self.bot.pg.executemany("DELETE FROM modlog_messages WHERE message_id = $1;", list(payload.message_ids))

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: commands.RawMessageUpdateEvent):
        msg = await self.bot.pg.fetchrow("SELECT * FROM modlog_messages WHERE message_id = $1", payload.message_id)
        if msg is None:
            return

        guild = self.bot.get_guild(msg['guild_id'])
        author = self.bot.get_user(msg['user_id'])
        if author.bot:
            return

        state = self.get_state(guild)
        if state is None or not state.message_edit:
            return

        try:
            message = await self.bot.get_channel(msg['channel_id']).fetch_message(msg['message_id']) #type: commands.Message
        except commands.HTTPException:
            return # doesnt exist?

        if message.content == msg['content']:
            return

        await self.bot.pg.execute("UPDATE modlog_messages SET content=$1 WHERE message_id = $2", message.content,
                                  message.id)

        embed = self.get_embed()
        embed.title = "Message Edited"
        embed.description = f"<:messageupdate:684549899039408179> {message.author.mention} - {message.author}"
        embed.add_field(name="Before", value=msg['content'])
        embed.add_field(name="After", value=message.content)
        embed.set_footer(text=f"id: {message.author.id}")

        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        state = self.get_state(channel.guild)

        if state is None or not state.channel_create:
            return

        embed = self.get_embed(commands.Color.green())
        embed.title = "Channel Created"
        embed.description = f"<:channelcreate:684549891279683657> {channel.mention if isinstance(channel, commands.TextChannel) else channel.name}"
        embed.set_footer(text=f"channel id: {channel.id}")

        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        state = self.get_state(channel.guild)
        if state is None or not state.channel_delete:
            return

        embed = self.get_embed(commands.Color.red())
        embed.title = "Channel Deleted"
        embed.description = f"<:channeldelete:684549913883050042> {channel.name}"
        embed.set_footer(text=f"channel id: {channel.id}")

        if self.has_permission(channel.guild):
            log = await self.get_audit_logs(channel.guild, limit=1, action=commands.AuditLogAction.channel_delete)
            log = log[0]
            embed.description += f"\ndeleted by: {log.user}"

        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if "member count" in after.name.lower():
            return

        if self.bucket.update_rate_limit(after):
            return

        state = self.get_state(after.guild)
        if state is None or not state.channel_edit:
            return

        diff = await self.iterate_channel_diff(before, after)
        embed = self.get_embed()
        embed.title = "Channel Updated"
        embed.description = f"<:channelupdate:684549910871277574> {after.mention}\n{diff}"
        embed.set_footer(text=f"channel id: {after.id}")
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        state = self.get_state(role.guild)
        if state is None or not state.role_create:
            return

        embed = self.get_embed(commands.Color.green())
        embed.title = "Role Created"
        embed.description = f"<:rolecreate:684549897277407249> {role.mention} - {role.name}"
        embed.set_footer(text=f"role id: {role.id}")
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        state = self.get_state(role.guild)
        if state is None or not state.role_delete:
            return

        embed = self.get_embed(commands.Color.red())
        embed.title = "Role Deleted"
        embed.description = f"<:roleremove:684549900913868805> {role.name}"
        embed.set_footer(text=f"role id: {role.id}")
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.permissions == after.permissions and before.name == after.name:
            return

        state = self.get_state(after.guild)
        if state is None or not state.role_edit:
            return

        embed = self.get_embed()
        embed.title = "Role Updated"
        embed.description = f"<:roleupdate:684549895327186978> {after.mention} - {after.name}\nbefore: {before.name}\nafter: {after.name}"
        embed.set_footer(text=f"role id: {after.id}")
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        state = self.get_state(guild)
        if state is None or not state.emojis_update:
            return

        diff = await self.find_emoji_diff(before, after)
        embed = self.get_embed()
        embed.description = diff
        embed.title = "Emojis Updated"
        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        state = self.get_state(guild)
        if state is None:
            return

        if not state.member_ban:
            return

        embed = self.get_embed(color=commands.Color.red())
        embed.title = "User Banned"
        embed.description = f"<:bancreate:684549908211957787> {user}\n"
        embed.set_footer(text=f"id: {user.id}")

        if not self.has_permission(guild):
            embed.description += "(I Can't see the audit logs. Unable to determine responsible moderator)"
            await self.send_to_channel(state, embed=embed)
            return

        log = await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.ban)
        log = log[0]
        embed.add_field(name="Moderator", value=f"{log.user.mention} - {log.user} (id: {log.user.id})")
        await self.send_to_channel(state, embed=embed)


    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        state = self.get_state(guild)
        if state is None or not state.member_unban:
            return

        embed = self.get_embed(commands.Color.green())
        embed.title = "User Unbanned"
        embed.description = f"<:bandelete:684549893913706527> {user}"
        embed.set_footer(text=f"id: {user.id}")

        if not self.has_permission(guild):
            embed.description += "\n(Unable to find unbanner. I can't see the audit logs!)"
            await self.send_to_channel(state, embed=embed)
            return

        logs = (await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.unban))[0]

        embed.add_field(name="Moderator", value=str(logs.user))

    async def on_member_mute(self, guild, user, length, mod="Unknown Moderator", reason="Unknown Reason"):
        state = self.get_state(guild)
        if state is None:
            return

        embed = self.get_embed(commands.Color.red())
        embed.title = "User Muted"
        embed.description = f"{user} was muted for {length} by {mod} for: {reason}"
        embed.set_footer(text=f"id: {user.id}")

        await self.send_to_channel(state, embed=embed)

    async def on_member_unmute(self, guild, user, mod="Unknown Moderator", reason="Unknown Reason"):
        state = self.get_state(guild)
        if state is None:
            return

        embed = self.get_embed(commands.Color.green())
        embed.title = "User Muted"
        embed.description = f"{user} was unmuted by {mod} for: {reason}"
        embed.set_footer(text=f"id: {user.id}")

        await self.send_to_channel(state, embed=embed)

    @commands.Cog.listener()
    async def on_warn(self, person, author, reason, guild, *_):
        state = self.get_state(guild)
        if state is None:
            return

        embed = self.get_embed()
        embed.title = "User Warned"
        embed.description = f"\U000026a0 {person} was warned by {author} for: {reason}"
        embed.set_footer(text=f"id: {person.id}")

        await self.send_to_channel(state, embed=embed)


    async def iterate_channel_diff(self, before: typing.Union[discord.VoiceChannel, discord.TextChannel],
                                   after: typing.Union[discord.VoiceChannel, discord.TextChannel])->str:
        ret = ""
        if before.name != after.name:
            ret += f"Name Changed: {before.name} -> {after.name}\n"

        if before.changed_roles != after.changed_roles or before.overwrites != after.overwrites:
            ret += f"Permissions Changed\n"

        if before.category_id != after.category_id:
            ret += f"Category Changed: {before.category.name} -> {after.category.name}\n"

        if before.position != after.position:
            ret += f"Position Changed: {before.position} -> {after.position}\n"

        if isinstance(after, discord.TextChannel) and before.slowmode_delay != after.slowmode_delay:
            ret += f"Slowmode Changed: {before.slowmode_delay} Seconds -> {after.slowmode_delay} Seconds\n"

        if before.topic != after.topic:
            ret += "Topic Changed"

        return ret

    async def find_emoji_diff(self, before: typing.List[discord.Emoji], after: typing.List[discord.Emoji])->str:
        ret = ""
        # first, look for deleted emojis
        for emoji in before:
            if discord.utils.get(after, id=emoji.id) is None:
                ret += f"<:emoteremove:460538983965786123> {emoji.name}\n"

        # next look for added emojis
        for emoji in after:
            if discord.utils.get(before, id=emoji.id) is None:
                ret += f"<:emotecreate:460538984263581696> {emoji.name} -> {emoji}\n"

        # next look for edited emojis
        for emoji in before:
            now = discord.utils.get(after, id=emoji.id)
            if now is not None and now.name != emoji.name:
                ret += f"<:emoteupdate:460539246508507157> {now} | {emoji.name} -> {now.name}"

        return ret