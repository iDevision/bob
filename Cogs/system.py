import calendar
import datetime
import os
import sys
import time
import traceback

import discord
import humanize
import psutil
import typing
import logging
import tabulate
from discord.ext import tasks

from utils import checks, errors, commands, paginator, objects
from utils.objects import HOIST_CHARACTERS
import inspect
# run these now, because the first calls made to these return nothing useful.
psutil.cpu_percent()
psutil.getloadavg()

logger = logging.getLogger("discord.system")

MODULES = {
    "moderation": True,
    "quotes": True,
    "automod": True,
    "modlogs": True,
    "community": True,
    "fun": True,
    "music": True,
    "autoresponder": True,
    "misc": True,
    "events": True,
    "currency": True,
    "giveaway": True,
    "basics": True,
    "commands": True,
    "tags": True,
    "twitch": True,
    "highlight": True
}


def setup(bot):
    bot.on_command_error = on_command_error
    bot.add_cog(MyCog(bot))
    bot.add_cog(SystemCog(bot))

class SystemCog(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.loop_reminders.start()

    def cog_unload(self):
        self.loop_reminders.cancel()

    def cog_check(self, ctx):
        return ctx.bot.is_owner(ctx.author)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild, *args):
        await self.bot.pg.execute("INSERT INTO roles VALUES ($1,0,0,0,0,0)", guild.id)

    @commands.Cog.listener("on_message")
    async def afk_runner(self, message):
        if message.author.bot or message.guild is None:
            return

        if not message.mentions:
            return

        guild_afks = await self.bot.pg.fetch("SELECT * FROM afks WHERE guild_id = $1 ", message.guild.id)
        msg = ""

        for gid, uid, m in guild_afks:
            if uid == message.author.id:
                try:
                    await message.channel.send(f"{message.author.mention} --> welcome back! (removing your `AFK` state)")
                except:
                    pass

                return await self.bot.pg.execute("DELETE FROM afks WHERE user_id = $1 AND guild_id = $2", (message.author.id, message.guild.id))

            for i in message.mentions:
                if i.id == uid:
                    psn = message.guild.get_member(uid)
                    msg += f"{psn.display_name} is afk: {msg}\n"

        if msg:
            msg = msg.strip()
            if '\n' in msg:
                msg = "\n" + msg

            await message.channel.send(f"hey {message.author.mention}! {msg}")

    @tasks.loop(seconds=5)
    async def loop_reminders(self):
        if not self.bot.is_ready():
            return

        rems = await self.bot.pg.fetch("SELECT * FROM reminders WHERE remind_time <= $1", datetime.datetime.utcnow())
        if not rems:
            return

        for gid, cid, msg, remindtime, link, uid in rems:
            if remindtime <= datetime.datetime.utcnow():
                chan = self.bot.get_channel(cid)
                if chan:
                    await chan.send(f"Hey <@{uid}>! Here's a reminder: {msg}\n\noriginal message: {link}")

        await self.bot.pg.execute("DELETE FROM reminders WHERE remind_time <= $1", datetime.datetime.utcnow())

    @commands.Cog.listener()
    async def on_unmute(self, data: dict):
        member = self.bot.get_guild(data['guild_id']).get_member(data['user'])
        await member.remove_roles(discord.Object(id=data['role_id']))
        logging = self.bot.get_cog("logging")
        if not logging:
            return

        await logging.on_member_unmute(discord.Object(id=data['guild_id']), member, mod=str(self.bot.user), reason="Auto")

    @commands.group("system", invoke_without_command=True, usage="[subcommand]", aliases=['sys', 'dev'])
    async def system(self, ctx):
        pass

    @system.command()
    async def reloadconfig(self, ctx):
        self.bot.reload_settings()
        await ctx.message.add_reaction("\U0001f44d")

    @system.command(aliases=['block', 'hammer'])
    async def ban(self, ctx, user: typing.Union[discord.User, int], *, reason="None Given"):
        """
        ban a user from the bot
        """
        await self.bot.pg.execute("INSERT INTO bans VALUES ($1,$2)", user.id if isinstance(user, discord.User) else user, reason)
        self.bot.bans[user.id if isinstance(user, discord.User) else user] = reason
        await ctx.send(f"{str(user)} has been banned from BOB")

    @system.command(aliases=['unblock', 'unhammer'])
    async def unban(self, ctx, user: typing.Union[discord.User, int]):
        """
        unban a user from the bot
        """
        if not (user.id if not isinstance(user, int) else user) in self.bot.bans:
            return await ctx.send("That user is not banned")
        del self.bot.bans[user.id if not isinstance(user, int) else user]
        await self.bot.pg.execute("DELETE FROM bans WHERE user_id = $1", user.id if not isinstance(user, int) else user)
        await ctx.send(f"unbanned user {user}")

    @system.command("stats", usage="(no parameters)")
    async def sysstats(self, ctx):
        """
        use this to see the stats of the system
        """
        e = discord.Embed(color=discord.Color.teal(), timestamp=datetime.datetime.utcnow())
        mem = psutil.virtual_memory()
        v = f"used = `{round(mem.used*0.000000001, 2)}` GB\n" \
            f"available = `{round(mem.available*0.000000001, 2)}` " \
            f"GB\nfree = `{round(mem.free*0.000000001, 2)}` GB\n" \
            f"total = `{round(mem.total*0.000000001, 2)}` GB"
        e.add_field(name="System Memory", value=v)
        del mem
        dsk = psutil.disk_usage(os.path.dirname(os.path.dirname(__file__)))
        v = f"free = `{round(dsk.free*0.000000001, 2)}` GB\nused = `{round(dsk.used*0.000000001, 2)}` GB\n" \
            f"total = `{round(dsk.total*0.000000001, 2)}` GB"
        e.add_field(name="Disk Info", value=v)
        del dsk
        cpu = psutil.cpu_percent()
        e.add_field(name="Cpu Usage", value=f"{cpu}%")
        del cpu
        ldavg = psutil.getloadavg()
        e.add_field(name="Load Average", value=str(ldavg[2]))
        del ldavg
        try:
            e.add_field(name="Wavelink Players", value=str(len(self.bot.wavelink.players)))
        except: pass
        proc = psutil.Process()
        with proc.oneshot():
            mem = proc.memory_full_info()
            e.add_field(name="Physical Memory", value=f"Using {humanize.naturalsize(mem.rss)} physical memory\n"
                           f"{humanize.naturalsize(mem.uss)} unique")
            e.add_field(name="Virtual Memory", value=f"{humanize.naturalsize(mem.vms)}")

            pid = proc.pid
            thread_count = proc.num_threads()
            e.add_field(name="PID", value=str(pid))
            e.add_field(name="Thread Count", value=str(thread_count))
        e.add_field(name="Python Version", value=str(sys.version))
        e.add_field(name="Platform", value=sys.platform)
        await ctx.send(embed=e)

    @system.command("quit", aliases=['kys', "die"])
    async def quit_bot(self, ctx):
        await ctx.send(f"{ctx.author.mention} --> shutting down.")
        await self.bot.close()

    @system.command("load", aliases=["r", "reload", "l"])
    async def reloads(self, ctx, module: str = None):
        if not module:
            await ctx.send(f"{ctx.author.mention} --> specify a module!")
            return
        module = "Cogs." + module

        if module in self.bot.extensions:
            self.bot.reload_extension(module)
            await ctx.send(f"{ctx.author.mention} --> reloaded module {module}")
        else:
            try:
                self.bot.load_extension(module)
                await ctx.send(f"loaded {module}")
            except Exception as e:
                await ctx.send("failed to load module")
                traceback.print_exception(type(e), e, e.__traceback__)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def status(self, ctx, type="playing", *, status):
        if type == "playing":
            activity = commands.Game(name=status)
        elif type == "watching":
            activity = discord.Activity(name=status, type=commands.ActivityType.watching)
        else:
            activity = discord.Activity(name=status, type=commands.ActivityType.listening)
        await self.bot.change_presence(activity=activity)

    @system.command()
    async def cogs(self, ctx):
        f = ""
        for fn in sorted(os.listdir(os.path.join(".", "Cogs"))):
            if ".py" not in fn: continue
            if fn in ["help.py", "changelog.py"]:
                f += f"\U0001f4e5 - {fn.replace('.py', '')}\n"
                continue
            t = False
            for i in self.bot.extensions.values():
                if i.__name__.replace("Cogs.", "") == fn.replace(".py", ""):
                    f += f"\U0001f4e5 - {fn.replace('.py', '')}\n"
                    t = True
                    break
            if not t:
                f += f"\U0001f4e4 - {fn.replace('.py', '')}\n"
        await ctx.send(embed=ctx.embed(description=f))

    @system.command()
    async def logs(self, ctx, *, log=None):
        if log is None:
            l = sorted(os.listdir("logs"))
            pages = paginator.Pages(ctx, entries=l)
            return await pages.paginate()
        if os.path.exists("logs/"+log):
            with open(f"logs/{log}") as f:
                v = await ctx.bot.session.post("https://mystb.in/documents", data=f.read().encode())
                v = await v.json()
                await ctx.send(f"https://mystb.in/{v['key']}")

    @system.command()
    async def sql(self, ctx, db, *, query):
        multi = query.count(";") > 1
        meth = getattr(self.bot, db, None)
        if meth is None:
            return await ctx.send(f"No database found as {db}")
        if multi:
            meth = meth.execute
        else:
            meth = meth.fetch

        try:
            ret = await meth(query)
        except Exception as e:
            return await ctx.paginate_text(traceback.format_exc(), codeblock=True)
        if multi:
            return await ctx.paginate_text(ret, codeblock=True)
        if not ret:
            return await ctx.message.add_reaction(":GreenTick:609893073216077825")

        h = list(ret[0].keys())
        table = tabulate.tabulate([list(map(repr, k)) for k in ret], tablefmt='psql', headers=h)
        await ctx.paginate_text(table, codeblock=True)

### ==========================

async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (errors.CommandInterrupt, errors.ModuleDisabled)):
        return await ctx.send(error.message, delete_after=5)
    if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
        error = error.original
        if error.code in [50013, 403]:
            return await ctx.send("Missing permissions to call "+ctx.command.qualified_name)
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            return await ctx.send("Discord Error: "+error.text)
    if isinstance(error, checks.MissingRequiredRole):
        return await ctx.send(error.message)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"{ctx.author.mention} --> missing required argument(s)! `{error.param}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"{ctx.author.mention} --> bad input: "+error.args[0])
    elif isinstance(error, commands.CheckFailure):
        return await ctx.send(error.args[0])
    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"whoa there, slow down! ({round(error.retry_after)} remaining)", delete_after=2)
    elif isinstance(error, (commands.ArgumentParsingError, commands.ConversionError)):
        await ctx.send("Bad input: couldn't parse your arguments")
    elif isinstance(error, errors.BannedUser):
        await ctx.bot.get_cog("Bull").run_ban(ctx)
    elif isinstance(error, commands.CommandError) and not isinstance(error, commands.CommandInvokeError):
        await ctx.send(error.args[0])
    else:
        v = f"error:\n__message__:\n> id: {ctx.message.id}\n> content: {ctx.message.content}\n__guild__:\n> id: {ctx.guild.id}" \
                f"\n> name: {ctx.guild.name}\n__Author__:\n> name: {ctx.author}\n> id: {ctx.author.id}\n __error__:\n> class: {error.original.__class__.__name__}\n> args: {error.original.args}"
        track = traceback.format_exception(type(error.original), error.original, error.original.__traceback__)
        ctx.bot.command_logger.exception(inspect.cleandoc(f"""
Commmand Exception:
Author: {ctx.author} (id: {ctx.author.id})
Guild: {ctx.guild.name} (id: {ctx.guild.id}) (large: {ctx.guild.large})
{''.join(track)}
        """))
        e = discord.Embed(description=v +
                                        "\n\n```" +
                                        "".join(traceback.format_exception(
                                            type(error.original), error.original, error.original.__traceback__))+"\n```",
                          timestamp=datetime.datetime.utcnow())

        from libraries import keys
        c = getattr(keys, ctx.bot.settings['run_bot']+"_UHOH", 604803860611203072)
        try:
            print("".join(traceback.format_exception(
                                            type(error.original), error.original, error.original.__traceback__)))
            await ctx.bot.get_channel(c).send(embed=e)
        except Exception as e:
            await ctx.bot.get_channel(c).send(embed=commands.Embed(description=f"Error occurred, traceback too long\n\n{error.args}", timestamp=datetime.datetime.utcnow()))
            await ctx.send("something happened while running that command! The dev is on his way to fix it!")
        else:
            if not await ctx.bot.is_owner(ctx.author):
                await ctx.send("something happened while running that command! The dev is on his way to fix it!")
            else:
                await ctx.send(embed=e)

# ===========================================



class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop_messages.start()
        self.save_ws_latency.start()

    def cog_unload(self):
        self.loop_messages.cancel()
        self.save_ws_latency.cancel()

    @tasks.loop(minutes=1)
    async def save_ws_latency(self):
        if str(self.bot.latency) == "nan":
            self.bot.pings.append((datetime.datetime.utcnow(), 50)) #bs but whatever
        self.bot.pings.append((datetime.datetime.utcnow(), self.bot.latency * 1000))

    @tasks.loop(seconds=1)
    async def loop_messages(self):
        rm = []
        for gid, messages in self.bot.timed_messages.items():
            for id, msg in messages.items():
                if time.time() - msg['timesent'] > 5:
                    rm.append((gid, id))
        for gid, msgid in rm:
            del self.bot.timed_messages[gid][msgid]
        del rm

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{time.ctime()}: logged in as {self.bot.user}')
        print("caching data...")
        statusc = self.bot.get_channel(629167007807438858)
        statusc = await statusc.send(embed=discord.Embed(title="Connected", color=discord.Color.orange()))
        stats = []
        self.bot.uptime = datetime.datetime.utcnow()

        if self.bot.setup:
            return

        prefixes = await self.bot.pg.fetch("SELECT guild_id, prefix FROM prefixes;")

        for gid, pref in prefixes:
            if gid in self.bot.guild_prefixes:
                self.bot.guild_prefixes[gid].append(pref)

            else:
                self.bot.guild_prefixes[gid] = [pref]

        del prefixes

        bans = await self.bot.pg.fetch("SELECT user_id, reason FROM bans;")
        for i in bans:
            self.bot.bans[i['user_id']] = i['reason']

        del bans
        # first, cache the role states.
        states = await self.bot.pg.fetch("SELECT * FROM roles")

        for record in states:
            self.bot.guild_role_states[record['guild_id']] = {
                                                "editor": record['editor'],
                                                "muted": record['muted'],
                                                "moderator": record['moderator'],
                                                "manager": record['manager'],
                                              }

        # next, cache the module states from existing data.
        states = await self.bot.pg.fetch("SELECT guild_id, flags FROM modules")

        for record in states:
            self.bot.guild_module_states[record['guild_id']] = objects.load_modules(record)

        vals = await self.bot.pg.fetch("SELECT * FROM stream_announcer")
        for record in vals:
            self.bot.streamers[record['guild_id']] = {"channel": record['channel'], "ids": record['users'], "message": record['message']}

        del vals

        # next, build the tables for the guilds joined during downtime (if any).
        for guild in self.bot.guilds:
            if guild.id not in self.bot.guild_prefixes:
                # all the cogs have their own on_guild_join method for creating new database rows.
                print("dispatching on_guild_join for server: "+str(guild.name))
                self.bot.dispatch("guild_join", guild, False) # im assuming if the prefix isnt there that nothing is there
                self.bot.guild_prefixes[guild.id] = ["!"]
                continue

            if guild.id not in self.bot.guild_module_states:
                mods = await self.bot.pg.fetchrow("INSERT INTO modules VALUES ($1, $2) RETURNING *", guild.id,
                                                 objects.save_modules({}))
                self.bot.guild_module_states[guild.id] = objects.load_modules(mods)

            if guild.id not in self.bot.guild_role_states:
                self.bot.guild_role_states[guild.id] = {"editor": 0, "muted": 0, "manager": 0, "moderator": 0}
                await self.bot.pg.execute("INSERT INTO roles VALUES ($1, null, null, null, null)", guild.id)

        self.bot.setup = True
        print(f"{':'.join(time.strftime('%H %M %S').split())} cache built.")
        e = discord.Embed(title="Connected", color=discord.Color.green())
        for a, b in stats:
            e.add_field(name=a, value=b)

        await statusc.edit(embed=e)

    @commands.Cog.listener()
    async def on_disconnect(self):
        print(f"{time.ctime()}: disconnected from discord")

    @commands.Cog.listener()
    async def on_shard_ready(self, shard_id: int):
        print(f"{time.ctime()} - shard ready: {shard_id}")

    @commands.Cog.listener()
    async def on_shard_disconnect(self, shard_id):
        print(f"{time.ctime()} - lost connection: shard: {shard_id}")

    @commands.Cog.listener()
    async def on_member_join(self, member, silence=False):
        if silence:
            return

        if not member.guild.me.guild_permissions.manage_roles and not member.guild.me.guild_permissions.administrator:
            return

        roles = await self.bot.pg.fetch("SELECT role_id FROM role_assign WHERE guild_id = $1", member.guild.id)
        if roles:
            robj = []
            for role in roles:
                v = member.guild.get_role(role[0])
                if not v:
                    continue

                robj.append(v)

            await member.add_roles(*robj)

        muted = await self.bot.pg.fetch("SELECT user_id FROM mutes WHERE guild_id = $1 AND user_id = $2", member.guild.id, member.id)
        if muted:
            m = member.guild.get_role(self.bot.guild_role_states[member.guild.id]['muted'])
            if m:
                await member.add_roles(m)


    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild, pres=True):
        self.bot.guild_prefixes[guild.id] = ["!"] if self.bot.run_bot != "BOB_ALPHA" else ["]"]
        self.bot.guild_role_states[guild.id] = {"editor": None, "muted": None, "moderator": None, "manager": None,
                                            "streamer": None}
        async with self.bot.pg.acquire() as conn:
            mods = await conn.fetchrow("INSERT INTO modules VALUES ($1, $2) RETURNING *", guild.id, objects.save_modules({}))
            self.bot.guild_module_states[guild.id] = objects.load_modules(mods)
            await conn.execute("INSERT INTO roles VALUES ($1, null, null, null, null)", guild.id)
            await conn.execute("INSERT INTO prefixes VALUES ($1,$2)", guild.id, "!")

        self.bot.guild_role_states[guild.id] = {"editor": 0, "muted": 0, "manager": 0, "moderator": 0}
        fmt = f"**__Guild Joined__**\nname: {guild.name}\nid: {guild.id}\nowner: {guild.owner}\n\nMembers: {len(guild.members)}"
        e = commands.Embed(description=fmt, color=discord.Color.teal())
        await self.bot.get_channel(662176688150675476).send(embed=e)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        del self.bot.guild_prefixes[guild.id]
        del self.bot.guild_module_states[guild.id]
        async with self.bot.pg.acquire() as conn:
            await conn.execute("DELETE FROM roles WHERE guild_id = $1", guild.id)
            await conn.execute("DELETE FROM modules WHERE guild_id = $1", guild.id)
            await conn.execute("DELETE FROM prefixes WHERE guild_id = $1", guild.id)

        fmt = f"**__Guild Left__**\nname: {guild.name}\nid: {guild.id}\nowner: {guild.owner}\n\nMembers: {len(guild.members)}"
        e = commands.Embed(description=fmt, color=commands.Color.red())
        await self.bot.get_channel(662176688150675476).send(embed=e)

    @commands.Cog.listener()
    async def on_member_update(self, _, after: commands.Member):
        if after.bot:
            return

        if after.guild.me.guild_permissions.manage_nicknames or after.guild.me.guild_permissions.administrator:
            if not any([x.hoist for x in after.roles]):
                if after.display_name.startswith(HOIST_CHARACTERS):
                    await after.edit(nick="Hoister no hoisting")
