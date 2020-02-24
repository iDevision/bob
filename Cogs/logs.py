import datetime
import time
import typing
import discord

from utils import btime, commands


def setup(bot):
    bot.add_cog(logging(bot))


class logging(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("_modlogs").db
        self.bucket = commands.CooldownMapping.from_cooldown(1,0.3,commands.BucketType.guild)

    def is_enabled(self, guild):
        return self.bot.guild_module_states[guild.id]['modlogs']

    def has_permission(self, guild):
        return guild.me.guild_permissions.view_audit_log

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild, *args):
        await self.db.execute("INSERT INTO modlogs VALUES (?,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0)", guild.id)

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.db.execute("DELETE FROM modlogs WHERE guild_id IS ?", guild.id)

    async def get_audit_logs(self, guild, limit=100, user=None, action=None):
        return await self.bot.get_guild(guild.id).audit_logs(limit=limit, user=user, action=action).flatten()

    async def log(self, title: str, description: str, fields: list, guild, footer=None, author=None, image=None,
                  color=None):
        # TODO: cache channels
        if not self.is_enabled(guild):
            return
        chan = await self.db.fetch("SELECT channel FROM modlogs WHERE guild_id IS ?", guild.id)
        channel = self.bot.get_channel(chan)
        if not channel:
            return
        e = discord.Embed(title=f"**{title.strip('*')}**", description=description)
        e.timestamp = datetime.datetime.utcnow()
        if not color:
            e.colour = discord.Color.teal()
        else:
            e.colour = color
        if footer:
            e.set_footer(text=footer[0], icon_url=footer[1])
        if author:
            e.set_author(name=author[0], icon_url=author[1])
        if image:
            e.set_thumbnail(url=image)
        for i in fields:
            e.add_field(name=i[0], value=i[1], inline=False)
        await channel.send(embed=e)

    @commands.Cog.listener()
    async def on_member_join(self, member, silence=False):
        if silence: return
        enabled = await self.db.fetch("SELECT member_join FROM modlogs WHERE guild_id IS ?", member.guild.id)
        if not enabled:
            return
        is_new = member.created_at > (datetime.datetime.utcnow() - datetime.timedelta(days=7))
        if is_new:
            await self.log("Member Joined", f"<:memberjoin:432986578755911680> {member.mention} - {member}",
                           [("New User Alert",f"<:alert:498095663729344514> Account created {btime.human_timedelta(member.created_at)}")],
                           member.guild, footer=(f"id: {member.id}", discord.Embed.Empty),
                           color=0xdda453)
        await self.log("Member Joined", f"<:memberjoin:432986578755911680> {member.mention} - {member}", [],
                       member.guild, footer=(f"id: {member.id}", discord.Embed.Empty),
                       color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        ml, mk, mb = await self.db.fetchrow("SELECT member_leave, member_iskicked, member_isbanned FROM modlogs WHERE guild_id IS ?",
                                        (member.guild.id,))
        if not self.has_permission(member.guild):
            return await self.log("**User Left**", f"<:memberleave:432986578672156673> {member}\n(unable to resolve leave/ban/kick. I can't see the audit logs!)", [], member.guild,
                           color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        klogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.kick)
        blogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.ban)
        try:
            klogs = klogs[0]
        except:
            try:
                if (datetime.datetime.utcnow() - blogs[0].created_at).total_seconds() > 3 and ml:
                    await self.log("**User Left**", f"<:memberleave:432986578672156673> {member}", [], member.guild,
                                   color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
                else:
                    return # its a ban. will be handled by on_member_ban
            except IndexError:
                if not ml:
                    return
                return await self.log("**User Left**", f"<:memberleave:432986578672156673> {member.mention} - {member}", [], member.guild,
                               color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        try:
            blogs = blogs[0]
        except:
            if (datetime.datetime.utcnow() - klogs.created_at).total_seconds() < 2:
                # must be a kick, theres no bans within the last 3 seconds.
                if not mk:
                    return
                return await self.on_member_kicketh(member, klogs.user) # user has been yeeted
        if klogs and time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(klogs.created_at.timetuple()) > 3 and \
                time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(blogs.created_at.timetuple()) > 3:
            # last kick and ban was more than 3 seconds ago, its probably not this event, so the user must have left voluntarily
            if not ml:
                return
            await self.log("**User Left**", f"<:memberleave:432986578672156673> {member.mention} - {member}", [], member.guild, color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        elif not klogs and (datetime.datetime.utcnow() - blogs.created_at).total_seconds() < 2:
            if not ml:
                return
            await self.log("**User Left**", f"<:memberleave:432986578672156673> {member.mention} - {member}", [], member.guild, color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        elif (datetime.datetime.utcnow() - klogs.created_at).total_seconds() < 2:
            if not mk:
                return
            await self.on_member_kicketh(member, klogs.user) # user has been yeeted

    async def on_member_kicketh(self, member, mod):
        enabled = await self.db.fetch("SELECT member_iskicked FROM modlogs WHERE guild_id IS ?", member.guild.id)
        if not enabled:
            return
        await self.log("**User Kicked**", f"<:memberleave:432986578672156673> {member.mention}\nname: {member}\nid: {member.id}",
                       [("Moderator", mod.mention + f" - name: {mod} (id: {mod.id})")], member.guild,
                       color=discord.Color.red())

    async def on_member_banish(self, member, mod, audit):
        enabled = await self.db.fetch("SELECT member_isbanned FROM modlogs WHERE guild_id IS ?", member.guild.id)
        if not enabled:
            return
        if audit is None:
            return await self.log("**User Banned**",
                                  "<:bancreate:432986579062226954> (Unable to resolve the moderator responsible, I can't see the audit logs!)",
                                  [
                                      ("User", f"{member.mention}\nname: {str(member)}\nid: {member.id}")],
                                  member.guild,
                                  color=discord.Color.red())
        await self.log("**User Banned**", f"<:bancreate:432986579062226954> member.mention\nname: {str(member)}\nid: {member.id}",
                        [("Moderator", mod.mention + f"\nname: {mod.name}\nid: {mod.id}\nreason: {audit.reason}")],
                        member.guild,
                        color=discord.Color.red())

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            enabled = await self.db.execute("SELECT member_nickname_change FROM modlogs WHERE guild_id IS ?", after.guild.id)
            if not enabled:
                return
            await self.log("Nickname Changed", f"<:memberupdate:432986577694883860> \n**Before:** {before.nick}\n**After:** {after.nick}",
                           [], before.guild, footer=(f"id: {after.id}", discord.Embed.Empty), author=(str(after),
                                                                                                  after.avatar_url))
        if before.roles != after.roles:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or message.guild is None:
            return
        if message.id in self.bot.logging_ignore:
            self.bot.logging_ignore.remove(message.id)
            return
        enabled = await self.db.fetch("SELECT message_delete FROM modlogs WHERE guild_id IS ?", message.guild.id)
        if not enabled:
            return
        if not self.has_permission(message.guild):
            return await self.log("**Message Deleted**", "(unable to determine who deleted the message, I can't see the audit logs!)",
                           [("content", message.content)], message.guild,
                           author=(str(message.author), message.author.avatar_url), color=discord.Color.magenta())
        logs = await self.get_audit_logs(message.guild, limit=1, action=discord.AuditLogAction.message_delete)
        try:
            logs = logs[0]
            if not logs.created_at < message.created_at: # i mean, this should work
                deleted = [("Deleted by", logs.user.mention + "\n" + str(logs.user)+f"\nid: {logs.user.id}")]
            else:
                deleted = []
        except:
            deleted = []
        await self.log("**Message Deleted**", f"<:messagedelete:432986578764300301>\n{message.content}", deleted, message.guild,
            author=(str(message.author), message.author.avatar_url), color=discord.Color.magenta())

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages[0].guild:
            return
        enabled = await self.db.fetch("SELECT message_delete FROM modlogs WHERE guild_id IS ?",
                                          messages[0].guild.id)
        if not enabled:
            return
        amo = len(messages)
        await self.log("Bulk messages deleted", messages[0].channel.mention, [("Amount", str(amo))], messages[0].guild)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.author.bot or before.content == after.content:
            return
        enabled = await self.db.fetch("SELECT message_edit FROM modlogs WHERE guild_id IS ?", after.guild.id)
        if not enabled:
            return
        bef = before.content
        aft = after.content
        await self.log("Message edited", after.channel.mention, [("Before", "``"+bef+"``"), ("After", "``"+aft+"``")],
                  after.guild, color=discord.Color.teal(), author=(after.author, after.author.avatar_url), footer=(f"user id: {after.author.id}", discord.Embed.Empty))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        enabled  = await self.db.fetch("SELECT channel_create FROM modlogs WHERE guild_id IS ?", channel.guild.id)
        if not enabled:
            return
        await self.log("Channel Created", f"<:channelcreate:432986578781077514> {channel.mention} | {channel.name}", [], channel.guild,
                       color=discord.Color.teal(), footer=("channel id: "+str(channel.id), channel.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        enabled = await self.db.fetch("SELECT channel_delete FROM modlogs WHERE guild_id IS ?", channel.guild.id)
        if not enabled:
            return
        await self.log("Channel Deleted", f"<:channeldelete:432986579674333215> {channel.name}", [], channel.guild,
                  footer=("channel id: "+str(channel.id), channel.guild.icon_url), color=discord.Color.teal())

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if "member count" in after.name.lower():
            return
        if self.bucket.update_rate_limit(after):
            return
        enabled = await self.db.fetch("SELECT channel_edit FROM modlogs WHERE guild_id IS ?", after.guild.id)
        if not enabled:
            return
        diff = await self.iterate_channel_diff(before, after)
        await self.log("Channel Updated", f"<:channelupdate:432986579196182550> {after.mention}\n{diff}", [], after.guild,
                  footer=("channel id: "+str(after.id), after.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        enabled = await self.db.fetch("SELECT role_create FROM modlogs WHERE guild_id IS ?", role.guild.id)
        if not enabled:
            return
        await self.log("New Role", f"<:rolecreate:432986578911232001> {role.mention}", [("Role Name", role.name), ("Hoisted", str(role.hoist)), ("ID", str(role.id))],
                  role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        enabled = await self.db.fetch("SELECT role_delete FROM modlogs WHERE guild_id IS ?", role.guild.id)
        if not enabled:
            return
        await self.log("Role Deleted", f"<:roleremove:432986578969952266> {role.name}", [],
                       role.guild, footer=(f"Role id: {role.id}", role.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.permissions == after.permissions and before.name == after.name:
            return
        enabled = await self.db.fetch("SELECT role_edit FROM modlogs WHERE guild_id IS ?", after.guild.id)
        if not enabled:
            return
        await self.log("Role Updated", f"<:roleupdate:432986578911232000> {after.name}", [
            ("before", f"name: {before.name}\nid: {before.id}\nhoisted: {before.hoist}"),
            ("after", f"name: {after.name}\nid: {after.id}\nhoisted: {after.hoist}")],
            after.guild, footer=(f"Role id: {str(after.id)}", after.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        enabled = await self.db.fetch("SELECT emojis_update FROM modlogs WHERE guild_id IS ?", guild.id)
        if not enabled:
            return
        diff = await self.find_emoji_diff(before, after)
        await self.log("Emojis Updated", diff, [], guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, member):
        if not self.has_permission(guild):
            return await self.on_member_banish(member, None, None)
        log = await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.ban)
        await self.on_member_banish(member, log[0].user, log[0])


    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        enabled = await self.db.fetch("SELECT member_isunbanned FROM modlogs WHERE guild_id IS ?", guild.id)
        if not enabled:
            return
        if not self.has_permission(guild):
            return await self.log("Member Unbanned", "<:bandelete:432986578848055299> Unable to resolve the moderator responsible, I can't see the audit logs!)",
                                  [("name", user.mention + " " + user.name+user.discriminator)],guild, color=discord.Color.green())
        logs = (await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.unban))[0]
        await self.log("Member Unbanned", "<:bandelete:432986578848055299>", [("name", user.mention + " " + user.name+user.discriminator),
                                               ("Moderator", logs.user.mention + " " + logs.user.name+logs.user.discriminator)],
            guild, footer=(logs.user.name, logs.user.avatar_url), image=logs.target.avatar_url, color=discord.Color.green())

    async def on_member_mute(self, guild, user, length, mod="Unknown Moderator", reason="Unknown Reason"):
        await self.log("Member muted", discord.Embed.Empty, [("User", user.mention + " | "+str(user)), ("Reason", reason), ("Length", length)], guild,
        footer=("User Id: "+str(user.id), discord.Embed.Empty), author=("Mute | "+str(mod), discord.Embed.Empty), color=discord.Color.red())

    async def on_member_unmute(self, guild, user, mod="Unknown Moderator", reason="Unknown Reason"):
        await self.log("Member unmuted", discord.Embed.Empty, [("Reason", reason), ("User", user.mention+" | "+str(user))], guild,
        footer=("User Id: "+str(user.id), discord.Embed.Empty), author=("Unmute | "+str(mod), discord.Embed.Empty))

    @commands.Cog.listener()
    async def on_warn(self, person, author, reason, guild, automod=None):
        e = discord.Embed(timestamp=datetime.datetime.now())
        e.colour = discord.Color.dark_red()
        e.set_author(name=f"{person.name} | warn", icon_url=person.avatar_url)
        e.set_footer(text=person.display_name + " | id: " + str(person.id), icon_url=person.avatar_url)
        e.add_field(name="moderator:", value=author.mention if not automod else guild.me.mention + " (AutoMod)",
                    inline=False)
        e.add_field(name="user: ", value=person.mention, inline=False)
        e.add_field(name="reason: ", value=reason, inline=False)
        chan = self.bot.get_channel(
            await self.db.fetch("SELECT mod_logs_channel FROM guild_configs WHERE guild_id IS ?", guild.id))
        if chan is not None:
            await chan.send(embed=e)

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
        if before.slowmode_delay != after.slowmode_delay:
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