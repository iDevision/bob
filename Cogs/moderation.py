import datetime
import typing

import discord

from utils import btime, db, commands
from utils.checks import *


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
        self.db = db.Database("moderation")

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.db.execute("DELETE FROM warnings WHERE guild_id IS ?", guild.id)

    async def cog_check(self, ctx):
        return await basic_check(ctx, "moderator", "editor")

    @commands.command(usage="<target>")
    @check_moderator()
    async def kick(self, ctx, target: discord.User):
        """
        kicks a user from the server.
        requires the `moderator` role or higher
        """
        await ctx.guild.kick(target)

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
            await ctx.send(f"banned user with id: {target.id}")
        else:
            await ctx.guild.ban(target)
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
    @check_moderator()
    async def _warn(self, ctx, person: discord.Member, *, reason: str = "None Given"):
        """
        warn a user. warnings show up on a users profile card.
        requires the `moderator` role or higher.
        additionally, warnings can be seen individually using !warnings
        """
        v = await self.on_warn(person, ctx.author, reason, ctx.guild, ctx.message)
        await ctx.send("successfully warned {0}.".format(str(person)+v))

    async def on_warn(self, person, author, reason, guild, automod=None):
        amo = await self.db.fetchall("SELECT * FROM warnings WHERE guild_id IS ? AND user_id IS ?",
                                      guild.id, person.id)
        if not amo:
            amo = 1
        else:
            amo = len(amo) + 1

        await self.db.execute("INSERT INTO warnings VALUES (?,?,?,?,?)",
                                (guild.id, person.id, author.id, reason, amo))
        try:
            await person.send("you have been warned in {0.name} for: {1}".format(guild, reason))
        except:
            pass
        t = round(datetime.datetime.utcnow().timestamp())
        await self.db.execute("INSERT INTO moddata VALUES (?,?,?,?,?)", (guild.id, person.id, author.id, f"User Warned (auto data log)", t))
        return await self.will_mute(person, guild, amo)

    async def will_mute(self, member, guild, amount):
        if amount in [3,6,9,12,15,18,21]:
            v = self.bot.guild_role_states[guild.id]['muted']
            if not v:
                return f"(Failed to mute user for {amount} warnings. no mute role set up.)"
            try:
                await member.add_roles(discord.Object(id=v))
            except:
                return f"(lacking permission to mute user for {amount} of warnings)"
            return f"(muted user for {amount} warnings)"
        return ""

    @commands.command()
    @check_moderator()
    async def moddata(self, ctx, user:commands.Member):
        """
        view all moderation actions done to the user (including automod), and any logs made by other moderators using loguser
        """
        data = await self.db.fetchall("SELECT * FROM moddata WHERE user_id IS ? AND guild_id IS ?", user.id, ctx.guild.id)
        if data is None:
            emb = ctx.embed(description=f"{user.mention} - __{user}__\nNo logs found.")
            return await ctx.send(embed=emb)
        formatted = f"{user.mention} - __{user}__\n\n"
        for i in data:
            t = datetime.datetime.fromtimestamp(i[4],tz=datetime.timezone.utc)
            newline = '\n' # >:(
            s = f"log from <@{i[2]}> at {t.strftime('%c')} UTC:\n> {i[3].replace(newline, newline+'> ')}"
            formatted += s+"\n\n"
        emb = ctx.embed(description=formatted)
        await ctx.send(embed=emb)

    @commands.command()
    async def loguser(self, ctx, user: discord.Member, *, text):
        """
        put a moderation entry on a person. you can view all entries on a person by using !moddata
        """
        t = round(datetime.datetime.utcnow().timestamp())
        await self.db.execute("INSERT INTO moddata VALUES (?,?,?,?,?)", (ctx.guild.id, user.id, ctx.author.id, text, t))
        await ctx.send(f"logged info for {user}")

    @commands.command("unmute", usage="<target> [reason]")
    @check_moderator()
    async def unmute(self, ctx, user: discord.Member, *, reason: commands.clean_content = None):
        """
        allows a user to talk again in the server.
        you must have the `moderator` role to use this command
        """
        r = await self.bot.db.fetch("SELECT muted FROM roles WHERE guild_id IS ?", ctx.guild.id)
        await user.remove_roles(discord.Object(id=r))
        await ctx.send(f"{ctx.author.mention} --> successfully unmuted {user.display_name}")
        t = round(datetime.datetime.utcnow().timestamp())
        await self.db.execute("INSERT INTO moddata VALUES (?,?,?,?,?)", (ctx.guild.id, user.id, ctx.author.id, "User Unmuted (auto data log)", t))
        logs = self.bot.get_cog("logging")
        if reason is None:
            reason = f'Action done by {ctx.author} (ID: {ctx.author.id})'
        await logs.on_member_unmute(ctx.guild, user, mod=ctx.author, reason=reason)

    @commands.command("mute")
    @check_moderator()
    async def _mute(self, ctx, member: discord.Member, *, reason: commands.clean_content = None):
        """
        mutes a member. note that a `Muted` role must be set for this to work.
        you must have the `Moderator` Role or higher to use this command
        you can unmute them with the `unmute` command.
        """
        mod = ctx.author
        if reason is None:
            reason = f'Action done by {mod} (ID: {mod.id})'
        role_id = await self.bot.db.fetch("SELECT muted FROM roles WHERE guild_id IS ?", ctx.guild.id)
        if not role_id:
            return await ctx.send("No Muted role set for your server! contact a Bot Editor to set one up!")
        await member.add_roles(discord.Object(id=role_id), reason=reason)
        logs = self.bot.get_cog("logging")
        await logs.on_member_mute(ctx.guild, member, "indefinite", reason=reason, mod=mod)
        await ctx.send(f"Muted {member}")
        t = round(datetime.datetime.utcnow().timestamp())
        await self.db.execute("INSERT INTO moddata VALUES (?,?,?,?,?)", (ctx.guild.id, member.id, ctx.author.id, "User Muted (auto data log)", t))

    @commands.command()
    @check_moderator()
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
        role_id = self.bot.guild_module_states[ctx.guild.id]['muted']
        await member.add_roles(discord.Object(id=role_id), reason=reason)
        await self.bot.schedule_timer(ctx.guild.id, "mute", duration.dt.timetuple(), user=member.id, reason=reason, role_id=role_id)
        delta = btime.human_timedelta(duration.dt, source=ctx.message.created_at)
        await ctx.send(f'Muted {member} for {delta}.')
        logs = self.bot.get_cog("logging")
        await logs.on_member_mute(ctx.guild, member, delta, reason=reason, mod=ctx.author)
        t = round(datetime.datetime.utcnow().timestamp())
        await self.db.execute("INSERT INTO moddata VALUES (?,?,?,?,?)", (ctx.guild.id, member.id, ctx.author.id, f"User Muted for {delta} (auto data log)", t))


    @commands.command("clearwarnings", usage="<target>")
    @check_moderator()
    async def clearwarnings(self, ctx, member: discord.Member):
        """
        removes all warnings from a user
        you must have the `moderator` role to use this command
        """
        await self.db.execute("DELETE FROM warnings WHERE guild_id IS ? AND user_id IS ?",
                                  ctx.guild.id, member.id)
        await ctx.send(f"{ctx.author.mention} --> cleared warnings for {member}")

    @commands.command()
    @check_moderator()
    @commands.cooldown(1, 120, commands.BucketType.guild)
    async def dehoist(self, ctx, nickname_only=False, *, new_nick="Don't Hoist"):
        """
        names all hoisters nicknames to "Don't Hoist" or a custom nickname
        """
        hoisters = []
        for member in ctx.guild.members:
            if nickname_only:
                if not member.nick: return
                name = member.nick
            else:
                name = member.display_name
            if not name[0].isalnum():
                await member.edit(nick=new_nick)
                hoisters.append(f"> {name} -- {member} -- {member.id}\n\n")
        if not hoisters:
            return await ctx.send("No hoisters found")
        e = ctx.embed_invis(title="Removed the following hoisters", description="".join(hoisters))
        await ctx.send(embed=e)

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
        except discord.Forbidden as e:
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
    async def remove(self, ctx, amount: int=100):
        """
        remove messages from chat, see `help remove` for more options
        """
        if await self.do_removal(ctx, amount, lambda m: True):
            await ctx.message.add_reaction("\N{THUMBS UP SIGN}")

    @remove.command()
    @check_moderator()
    async def user(self, ctx, user:commands.User, amount: int=100):
        """
        removes messages from a certain user
        """
        await self.do_removal(ctx, amount, lambda m: m.author == user, after=ctx.message)

    @remove.command(usage="<num>")
    @check_moderator()
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
