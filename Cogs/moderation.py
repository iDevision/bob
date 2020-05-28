import datetime
import typing
import json
import discord

from utils import btime, db, commands
from utils.checks import *
from utils.objects import HOIST_CHARACTERS


def setup(bot):
    bot.add_cog(moderation(bot))

class moderation(commands.Cog):
    """
    contains moderator commands. helps to make your mods' lives easier.
    requires the `moderator` role or higher to use.
    """
    category="moderation"
    def __init__(self, bot):
        self.bot = bot

    @commands.command(usage="<target>")
    @check_moderator()
    async def kick(self, ctx, target: discord.User, *, reason: commands.clean_content=None):
        """
        kicks a user from the server.
        requires the `moderator` role or higher
        """
        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, target.id, ctx.author.id,
                                  f"User Kicked (auto data log)", datetime.datetime.utcnow())
        await ctx.guild.kick(target, reason=reason)

    @commands.command(usage="<target>")
    @check_moderator()
    async def ban(self, ctx, target: typing.Union[discord.User, int], *, reason: commands.clean_content=None):
        """
        bans a user from the server.
        requires the `moderator` role or higher.
        if they are still in the server, @mentions will work.
        if not, use their id.
        """
        if isinstance(target, int):
            target = discord.Object(id=target)
            await ctx.guild.ban(target, reason=reason)
            await ctx.send(f"banned user with id: {target.id}")
        else:
            await ctx.guild.ban(target, reason=reason)
            await ctx.send(f"banned {target}")

    @commands.command(aliases=['newmembers'])
    @commands.guild_only()
    async def newusers(self, ctx, *, count=5):
        """Tells you the newest members of the server.
        """
        count = max(min(count, 25), 5)

        if not ctx.guild.chunked:
            await self.bot.request_offline_members(ctx.guild)
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at, reverse=True)[:count]
        e = discord.Embed(title='New Members', colour=discord.Colour.green())
        for member in members:
            data = f'Joined Server at {btime.human_timedelta(member.joined_at)}\nAccount created at {btime.human_timedelta(member.created_at)}'
            e.add_field(name=f'{member} ({member.id})', value=data)

        await ctx.send(embed=e)


    @commands.command("warn",usage="<user> [reason]")
    @check_module("moderation")
    @check_moderator()
    async def _warn(self, ctx, person: discord.Member, *, reason: str = "None Given"):
        """
        warn a user. warnings show up on a users profile card.
        requires the `moderator` role or higher.
        additionally, warnings can be seen individually using !warnings
        """
        try:
            await person.send("you have been warned in {0.name} for: {1}".format(ctx.guild, reason))
        except:
            pass

        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, person.id, ctx.author.id,
                                  f"User Warned (auto data log)", datetime.datetime.utcnow())
        await ctx.send(f"successfully warned {person}")

    @commands.command()
    @check_moderator()
    @check_module("moderation")
    async def notes(self, ctx, user:commands.Member):
        """
        view all moderation actions done to the user (including automod), and any logs made by other moderators using addnote
        """
        data = await self.bot.pg.fetch("SELECT * FROM moddata WHERE user_id = $1 AND guild_id = $2", user.id, ctx.guild.id)
        if not data:
            emb = ctx.embed(description=f"{user.mention} - __{user}__\nNo logs found.")
            return await ctx.send(embed=emb)

        formatted = [f"{user.mention} - __{user}__\n\n"]
        for record in data:
            newline = '\n' # >:( frickin fstrings
            s = f"log from <@{record['moderator_id']}> at {record['time'].strftime('%c')} UTC:\n> {record['note'].replace(newline, newline+'> ')}"
            formatted.append(s+"\n\n")
        await ctx.paginate(formatted)

    @commands.command()
    @check_module("moderation")
    @check_moderator()
    async def addnote(self, ctx, user: discord.Member, *, text):
        """
        put a moderation note on a person. you can view all entries on a person by using !notes <user>
        """
        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, user.id, ctx.author.id, text, datetime.datetime.utcnow())
        await ctx.send(f"logged info for {user}")

    @commands.command("unmute", usage="<target> [reason]")
    @check_moderator()
    @check_module("moderation")
    async def unmute(self, ctx, user: discord.Member, *, reason: commands.clean_content = None):
        """
        allows a user to talk again in the server.
        you must have the `moderator` role to use this command
        """
        role = ctx.guild.get_role(self.bot.guild_role_states[ctx.guild.id]['muted'])
        if not role:
            return await ctx.send("No mute role set up!")

        await user.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} --> successfully unmuted {user.display_name}")
        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, user.id, ctx.author.id, "User Unmuted (auto data log)", datetime.datetime.utcnow())
        logs = self.bot.get_cog("logging")
        if reason is None:
            reason = f'Action done by {ctx.author} (ID: {ctx.author.id})'

        await logs.on_member_unmute(ctx.guild, user, mod=ctx.author, reason=reason)

    @commands.command("mute")
    @check_moderator()
    @check_module("moderation")
    async def _mute(self, ctx, member: discord.Member, *, reason: commands.clean_content(fix_channel_mentions=True) = None):
        """
        mutes a member. note that a `Muted` role must be set for this to work.
        you must have the `Moderator` Role or higher to use this command
        you can unmute them with the `unmute` command.
        """
        mod = ctx.author
        if reason is None:
            reason = f'Action done by {mod} (ID: {mod.id})'

        role = ctx.guild.get_role(self.bot.guild_role_states[ctx.guild.id]['muted'])
        if not role:
            return await ctx.send("No Muted role set for your server! contact a Bot Editor to set one up!")

        await member.add_roles(role, reason=f"action done by {ctx.author}: {reason}")
        logs = self.bot.get_cog("logging")
        await logs.on_member_mute(ctx.guild, member, "indefinite", reason=reason, mod=mod)
        await ctx.send(f"Muted {member}")
        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, member.id, ctx.author.id, "User Muted (auto data log)", datetime.datetime.utcnow())
        await self.bot.pg.execute("INSERT INTO mutes VALUES ($1,$2,null);", ctx.guild.id, member.id)

    @commands.command()
    @check_moderator()
    @check_module("moderation")
    async def tempmute(self, ctx, member: discord.Member, duration: btime.FutureTime, *, reason: commands.clean_content = None):
        """Temporarily mutes a member for the specified duration.
        you must have the `moderator` role to use this command
        The duration can be a a short time form, e.g. 30d or a more human
        duration such as "until thursday at 3PM" or a more concrete time
        such as "2024-12-31".
        Note that times are in UTC.
        """
        if reason is None:
            reason = f'Action done by {ctx.author} (ID: {ctx.author.id})'

        role = ctx.guild.get_role(self.bot.guild_role_states[ctx.guild.id]['muted'])
        if not role:
            return await ctx.send("No mute role set")

        await member.add_roles(role, reason=reason)
        await self.bot.schedule_timer(ctx.guild.id, "unmute", duration.dt.timetuple(), user=member.id, reason=reason, role_id=role.id)
        delta = btime.human_timedelta(duration.dt, source=ctx.message.created_at)
        await ctx.send(f'Muted {member} for {delta}.')

        logs = self.bot.get_cog("logging")
        await logs.on_member_mute(ctx.guild, member, delta, reason=reason, mod=ctx.author)

        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", ctx.guild.id, member.id, ctx.author.id, f"User Muted for {delta} (auto data log)", datetime.datetime.utcnow())


    @commands.command()
    @check_moderator()
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @check_module("moderation")
    async def dehoist(self, ctx, nickname_only: bool=False, *, new_nick="Don't Hoist"):
        """
        names all hoisters nicknames to "Don't Hoist" or a custom nickname
        """
        hoisters = []
        for member in ctx.guild.members:
            if nickname_only:
                if not member.nick:
                    continue

                name = member.nick
            else:
                name = member.display_name

            if name.startswith(HOIST_CHARACTERS):
                await member.edit(nick=new_nick)
                hoisters.append(f"- hoisted name: {name} | username: {member} | id: {member.id}")

        if not hoisters:
            return await ctx.send("No hoisters found")

        await ctx.paginate(hoisters, title="Removed the following hoisters")

    async def do_removal(self, ctx, limit, predicate, *, before=None, after=None):
        """
        this function was borrowed from Danny's RoboDanny
        """
        if limit > 2000:
            await ctx.send(f'Too many messages to search given ({limit}/2000)')
            return False
        if before is None:
            before = ctx.message
        else:
            before = discord.Object(id=before)

        if after is not None:
            after = discord.Object(id=after)
        try:
            deleted = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
        except discord.Forbidden:
            await ctx.send('I need the Manage Messages permission!')
            return False
        except discord.HTTPException as e:
            await ctx.send(f'Error: {e} (search too large?)')
            return False
        deleted = len(deleted)
        messages = f'removed {deleted} message{"s" if deleted < 1 else ""}'
        await ctx.send(messages, delete_after=7)
        return True

    @commands.group(invoke_without_command=True, aliases=['purge'])
    @check_moderator()
    @check_module("moderation")
    async def remove(self, ctx, amount: int=100):
        """
        remove messages from chat, see `help remove` for more options
        """
        if await self.do_removal(ctx, amount, lambda m: True):
            await ctx.message.add_reaction("\N{THUMBS UP SIGN}")

        else:
            await ctx.message.add_reaction("\N{THUMBS DOWN SIGN}")

    @remove.command()
    @check_moderator()
    @check_module("moderation")
    async def user(self, ctx, user:commands.User, amount: int=100):
        """
        removes messages from a certain user
        """
        if await self.do_removal(ctx, amount, lambda m: m.author.id == user.id):
            await ctx.message.add_reaction("\N{THUMBS UP SIGN}")

    @remove.command()
    @check_moderator()
    @check_module("moderation")
    async def embeds(self, ctx, amount: int=100):
        """
        removes messages with embeds
        """
        if await self.do_removal(ctx, amount, lambda m: len(m.embeds) is not 0):
            await ctx.message.add_reaction("\N{THUMBS UP SIGN}")

    @remove.command(usage="<num>")
    @check_moderator()
    @check_module("moderation")
    async def reactions(self, ctx, search: int=100):
        """
        removes reactions from messages `num` amount of messages
        """
        if search > 2000:
            return await ctx.send(f'Attempted to search too many messages({search}/2000)')

        total_reactions = 0
        async for message in ctx.history(limit=search, before=ctx.message):
            if len(message.reactions):
                total_reactions += sum(r.count for r in message.reactions)
                await message.clear_reactions()

        await ctx.send(f'Successfully removed {total_reactions} reactions.')

    @commands.command()
    @check_moderator()
    @commands.bot_has_guild_permissions(manage_channels=True, )
    @check_module("moderation")
    async def lockdown(self, ctx, category: commands.CategoryChannel, *, lockdown_roles: commands.Greedy[commands.Role]=None):
        if lockdown_roles is None:
            lockdown_roles = [ctx.guild.default_role]

        elif not isinstance(lockdown_roles, list):
            lockdown_roles = [lockdown_roles, ctx.guild.default_role]

        else:
            lockdown_roles.append(ctx.guild.default_role)

        previous_role_overwrites = {}
        for channel in category.channels:
            overwrites = {}

            for thing, perms in channel.overwrites.items():
                if isinstance(thing, commands.Role) and thing.id in [x.id for x in lockdown_roles]:
                    overwrites[thing.id] = [perms.read_messages, perms.send_messages, perms.connect]

            for role in lockdown_roles:
                if role.id not in overwrites:
                    overwrites[role.id] = [role.permissions.read_messages, role.permissions.send_messages, role.permissions.connect]

            previous_role_overwrites[channel.id] = overwrites

        new_overwrites = {}
        perms = commands.PermissionOverwrite(read_messages=True, read_message_history=True, send_messages=False, connect=False)

        for role in lockdown_roles:
            new_overwrites[role] = perms

        try:
            await self.bot.pg.execute("INSERT INTO lockdowns VALUES ($1,$2,$3)", ctx.guild.id, category.id,
                                      json.dumps(previous_role_overwrites))
        except:
            return await ctx.send(f"the category {category} is already locked down!")

        for channel in category.channels:
            try:
                await channel.edit(overwrites=new_overwrites)
            except commands.HTTPException:
                await ctx.send(f"Failed to lock down {channel.mention}. aborting. (are any of the roles to lock above the bot's top role?)")
                await self.bot.pg.execute("DELETE FROM lockdowns WHERE category_id = $1", category.id)
                return

        roles = " | ".join(x.name for x in lockdown_roles if x.name != "@everyone")
        await ctx.send(f"The following roles have been locked out of {category.name}: default role | {roles}")

    @commands.command()
    @check_module("moderation")
    @check_moderator()
    async def unlockdown(self, ctx, category: commands.CategoryChannel):
        record = await self.bot.pg.fetchrow("DELETE FROM lockdowns WHERE guild_id = $1 AND category_id = $2 RETURNING overwrites;", ctx.guild.id, category.id)
        if not record:
            return await ctx.send(f"{category} is not locked down!")

        failed = []
        noexist = []
        overwrites = json.loads(record['overwrites'])
        await ctx.send(overwrites)

        for channel_id, values in overwrites.items():
            overwrites_with_objects = {}
            channel = ctx.guild.get_channel(int(channel_id))

            for role_id, read_and_write in values.items():
                overwrites_with_objects[ctx.guild.get_role(int(role_id))] = commands.PermissionOverwrite(
                    read_messages=read_and_write[0] if read_and_write[0] is False else True,
                    send_messages=read_and_write[1] if read_and_write[1] is False else True,
                    connect=read_and_write[2] if read_and_write[2] is False else True
                )

            try:
                await channel.edit(overwrites=overwrites_with_objects)
            except commands.HTTPException:
                failed.append(channel)


        if failed:
            if len(failed) == len(overwrites):
                await ctx.send("Failed to unlock channels, due to missing permissions! check that the roles that have been locked down are not above my highest role!")

            else:
                fail = ', '.join(channel.mention for channel in failed)
                await ctx.send(f"Unlocked some channels, but could not unlock {fail}")

        else:
            await ctx.send(f"All channels in {category.name} have been returned to their original state")


