import datetime
import time

import discord
from discord.ext import commands

from utils import btime


def setup(bot):
    bot.add_cog(logging(bot))


class logging(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("_modlogs").db

    @commands.Cog.listener()
    async def on_ready(self):
        pass

    def is_enabled(self, guild):
        return self.bot.guild_module_states[guild.id]['modlogs']

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
        e = discord.Embed(title=title, description=description)
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
            await self.log("Member Joined", f"{member.mention} - {member}",
                           [("New User Alert",f"Account created {btime.human_timedelta(member.created_at)}")],
                           member.guild, footer=(f"id: {member.id}", discord.Embed.Empty),
                           color=0xdda453)
        await self.log("Member Joined", f"{member.mention} - {member}", [], member.guild, footer=(f"id: {member.id}", discord.Embed.Empty),
                       color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        ml, mk, mb = await self.db.fetchrow("SELECT member_leave, member_iskicked, member_isbanned FROM modlogs WHERE guild_id IS ?",
                                        (member.guild.id,))
        klogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.kick)
        blogs = await self.get_audit_logs(member.guild, limit=1, action=discord.AuditLogAction.ban)
        try:
            klogs = klogs[0]
        except:
            try:
                if time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(blogs[0].created_at.timetuple()) > 3 and ml:
                    await self.log("**User Left**", f"{member.mention} - {member}", [], member.guild,
                                   color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
                else:
                    return # its a ban. will be handled by on_member_ban
            except IndexError:
                if not ml:
                    return
                return await self.log("**User Left**", f"{member.mention} - {member}", [], member.guild,
                               color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        try:
            blogs = blogs[0]
        except:
            if time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(klogs.created_at.timetuple()) > 3:
                # must be a kick, theres no bans within the last 3 seconds.
                if not mk:
                    return
                return await self.on_member_kicketh(member, klogs.user) # user has been yeeted
        if klogs and time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(klogs[0].created_at.timetuple()) > 3 and \
                time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(blogs.created_at.timetuple()) > 3:
            # last kick and ban was more than 3 seconds ago, its probably not this event, so the user must have left voluntarily
            if not ml:
                return
            await self.log("**User Left**", f"{member.mention} - {member}", [], member.guild, color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        elif not klogs and time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(blogs.created_at.timetuple()) > 3:
            if not ml:
                return
            await self.log("**User Left**", f"{member.mention} - {member}", [], member.guild, color=discord.Color.red(), footer=(f"id: {member.id}", discord.Embed.Empty))
        elif time.mktime(datetime.datetime.utcnow().timetuple()) - time.mktime(klogs.created_at.timetuple()) < 3:
            if not mk:
                return
            await self.on_member_kicketh(member, klogs.user) # user has been yeeted

    async def on_member_kicketh(self, member, mod):
        enabled = await self.db.fetch("SELECT member_iskicked FROM modlogs WHERE guild_id IS ?", member.guild.id)
        if not enabled:
            return
        await self.log("**User Kicked**", discord.Embed.Empty,
                       [("Moderator", mod.mention + f" - name: {mod} (id: {mod.id})"),
                        ("User", member.mention + f"\nname: {str(member)}\nid: {member.id}")], member.guild,
                       color=discord.Color.red())

    async def on_member_banish(self, member, mod):
        enabled = await self.db.fetch("SELECT member_isbanned FROM modlogs WHERE guild_id IS ?", member.guild.id)
        if not enabled:
            return
        await self.log("**User Banned**", discord.Embed.Empty,
                       [("Moderator", mod.mention + "\nname: " + str(mod.name) + "\nid: " + str(mod.id)),
                        ("User", member.mention + f"\nname: {str(member)}\nid: {member.id}")], member.guild,
                       color=discord.Color.red())

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            enabled = await self.db.execute("SELECT member_nickname_change FROM modlogs WHERE guild_id IS ?", after.guild.id)
            if not enabled:
                return
            await self.log("Nickname Changed", discord.Embed.Empty, [("**Before**", str(before.nick)),
                                                                     ("**After**", str(after.nick))],
                           before.guild, footer=(f"id: {after.id}", discord.Embed.Empty), author=(str(after),
                                                                                                  after.avatar_url))

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
        logs = await self.get_audit_logs(message.guild, limit=1, action=discord.AuditLogAction.message_delete)
        sets = [(str(message.author) + " - "+str(message.author.id), message.content)]
        try:
            logs = logs[0]
            if not logs.created_at < datetime.datetime.utcnow().replace(second=0): # i mean, this should work
                sets.append(("Deleted by", logs.user.mention + "\n" + str(logs.user)+f"\nid: {logs.user.id}"))
        except:
            pass
        await self.log("**Message Deleted**", discord.Embed.Empty, sets, message.guild,
            author=(str(message.author), message.author.avatar_url), color=discord.Color.magenta())

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages[0].guild:
            return
        enabled = await self.db.fetch("SELECT bulk_message_delete FROM modlogs WHERE guild_id IS ?",
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
        await self.log("Channel Created", channel.mention + " | "+channel.name, [], channel.guild,
                       color=discord.Color.teal(), footer=("channel id: "+str(channel.id), channel.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        enabled = await self.db.fetch("SELECT channel_delete FROM modlogs WHERE guild_id IS ?", channel.guild.id)
        if not enabled:
            return
        await self.log("Channel Deleted", channel.name, [], channel.guild,
                  footer=("channel id: "+str(channel.id), channel.guild.icon_url), color=discord.Color.teal())

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if "member count" in after.name.lower():
            return
        enabled = await self.db.fetch("SELECT channel_edit FROM modlogs WHERE guild_id IS ?", after.guild.id)
        if not enabled:
            return
        await self.log("Channel Updated", after.mention, [("**Before**", before.name), ("**After**", after.name)], after.guild,
                  footer=("channel id: "+str(after.id), after.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        enabled = await self.db.fetch("SELECT role_create FROM modlogs WHERE guild_id IS ?", role.guild.id)
        if not enabled:
            return
        await self.log("**New Role**", role.mention, [("Role Name", role.name), ("Hoisted", str(role.hoist)), ("ID", str(role.id))],
                  role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        enabled = await self.db.fetch("SELECT role_delete FROM modlogs WHERE guild_id IS ?", role.guild.id)
        if not enabled:
            return
        await self.log("**Role Deleted**", discord.Embed.Empty, [("role name", role.name),("role id", str(role.id))],
                       role.guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.permissions == after.permissions and before.name == after.name:
            return
        enabled = await self.db.fetch("SELECT role_edit FROM modlogs WHERE guild_id IS ?", after.guild.id)
        if not enabled:
            return
        await self.log("**Role Updated**", after.name, [
            ("before", f"name: {before.name}\nid: {before.id}\nhoisted: {before.hoist}"),
            ("after", f"name: {after.name}\nid: {after.id}\nhoisted: {after.hoist}")],
            after.guild, footer=(f"Role id: {str(after.id)}", after.guild.icon_url))

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        enabled = await self.db.fetch("SELECT emojis_update FROM modlogs WHERE guild_id IS ?", guild.id)
        if not enabled:
            return
        await self.log("**emojis updated**", "*(i dont know what else to put here? send suggestions with !idea)*", [], guild)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        log = await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.ban)
        await self.on_member_banish(user, log[0].user)


    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        enabled = await self.db.fetch("SELECT member_isunbanned FROM modlogs WHERE guild_id IS ?", guild.id)
        if not enabled:
            return
        logs = (await self.get_audit_logs(guild, limit=1, action=discord.AuditLogAction.unban))[0]
        await self.log("Member Unbanned", discord.Embed.Empty, [("**name**", user.mention + " " + user.name+user.discriminator),
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
