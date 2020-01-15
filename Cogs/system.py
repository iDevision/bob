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
from discord.ext import tasks

from utils import checks, errors, commands
from utils.checks import all_powerful_users

# run these now, because the first calls made to these return nothing useful.
psutil.cpu_percent()
psutil.getloadavg()


def setup(bot):
    bot.on_command_error = on_command_error
    bot.add_cog(MyCog(bot))
    bot.add_cog(SystemCog(bot))

class SystemCog(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.remindersdb = bot.get_cog("misc").remindersdb
        self.loop_reminders.start()
        self.bot.custom_listener(self.loop_mute)

    def cog_unload(self):
        self.loop_reminders.cancel()

    def cog_check(self, ctx):
        return ctx.author.id in all_powerful_users

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild, *args):
        await self.db.execute("INSERT INTO roles VALUES (?,0,0,0,0,0)", guild.id)
        await self.db.executemany("INSERT INTO guild_members VALUES (?,?,0,0)", [(guild.id, m.id) for m in guild.members])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.db.connection.executescript(f"DELETE FROM roles WHERE guild_id IS {guild.id}; DELETE FROM module_states"
                                               f" WHERE guild_id IS {guild.id}; DELETE FROM guild_members WHERE guild_id IS {guild.id}")
        await self.db.commit()

    @commands.Cog.listener("on_message")
    async def afk_runner(self, message):
        if message.author.bot or message.guild is None:
            return
        guild_afks = await self.bot.db.fetchall("SELECT * FROM afks WHERE guild_id IS ?", message.guild.id)
        msg = ""
        for gid, uid, m in guild_afks:
            if uid == message.author.id:
                await message.channel.send(f"{message.author.mention} --> welcome back! (removing your `AFK` state)")
                return await self.bot.db.execute("DELETE FROM afks WHERE user_id is ? AND guild_id IS ?", (message.author.id, message.guild.id))
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
        rems = await self.remindersdb.fetchall("SELECT * FROM reminders")
        if not rems:
            return
        dels = []
        for gid, cid, msg, remindtime, link, uid, uuid in rems:
            if remindtime <= calendar.timegm(datetime.datetime.utcnow().timetuple()):
                chan = self.bot.get_channel(cid)
                if chan:
                    await chan.send(f"Hey <@{uid}>! Here's a reminder: {msg}\n\noriginal message: {link}")
                dels.append((uuid,))
        v = await self.remindersdb.executemany("DELETE FROM reminders WHERE uuid IS ?", dels)

    async def loop_mute(self, data: dict):
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

    @system.command()
    async def ban(self, ctx, user: typing.Union[discord.User, int], *, reason="None Given"):
        """
        ban a user from the bot
        """
        await self.bot.db.execute("INSERT INTO bans VALUES (?,?)", user.id if isinstance(user, discord.User) else user, reason)
        self.bot.bans[user.id] = reason
        await ctx.send(f"{str(user)} has been banned from BOB")

    @system.command()
    async def unban(self, ctx, user: typing.Union[discord.User, int]):
        """
        unban a user from the bot
        """
        if not (user.id if not isinstance(user, int) else user) in self.bot.bans:
            return await ctx.send("That user is not banned")
        del self.bot.bans[user.id if not isinstance(user, int) else user]
        await self.bot.db.execute("DELETE FROM bans WHERE user_id IS ?", user.id if not isinstance(user, int) else user)
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
            e.add_field(name="Lavalink Players", value=str(len(self.bot.lavalink.players)))
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

    @system.command("quit", aliases=['kys'])
    async def quit_bot(self, ctx):
        await self.bot.pre_shutdown()
        await ctx.send(f"{ctx.author.mention} --> shutting down.")
        await self.bot.logout()

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


### ==========================

async def on_command_error(ctx: commands.Context, error):
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
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"{ctx.author.mention} --> missing required argument(s)! `{error.param}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"{ctx.author.mention} --> bad input: "+error.args[0])
    elif isinstance(error, commands.CheckFailure):
        return await ctx.send(error.args[0])
    elif isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"whoa there, slow down! ({round(error.retry_after)} remaining)", delete_after=2)
    elif isinstance(error, (commands.ArgumentParsingError, commands.ConversionError)):
        await ctx.send("Bad input; couldn't parse your arguments")
    elif isinstance(error, errors.BannedUser):
        await ctx.send(error.message)
    elif isinstance(error, commands.CommandError) and not isinstance(error, commands.CommandInvokeError):
        await ctx.send(error.args[0])
    else:
        v = f"error:\n__message__:\n> id: {ctx.message.id}\n> content: {ctx.message.content}\n__guild__:\n> id: {ctx.guild.id}" \
                f"\n> name: {ctx.guild.name}\n__Author__:\n> name: {ctx.author}\n> id: {ctx.author.id}\n __error__:\n> class: {error.original.__class__.__name__}\n> args: {error.original.args}"
        traceback.print_exception(type(error.original), error.original, error.original.__traceback__, file=sys.stderr)
        e = discord.Embed(description=v +
                                        "\n\n```" +
                                        "".join(traceback.format_exception(
                                            type(error.original), error.original, error.original.__traceback__)).replace("Angelo", "TMHK")+"\n```",
                          timestamp=datetime.datetime.utcnow())

        from libraries import keys
        c = getattr(keys, ctx.bot.settings['run_bot']+"_UHOH", 604803860611203072)
        try:
            await ctx.bot.get_channel(c).send(embed=e)
        except Exception as e:
            await ctx.send("couldn't alert the dev of your error due to: "+e.args[0])
        else:
            if not await ctx.bot.is_owner(ctx.author):
                await ctx.send("An error has occurred while running this command. The dev has been informed, and will fix it soon!")
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
        statusc = await statusc.send(embed=discord.Embed(title="Connected", color=discord.Color.orange(), description="loading..."))
        stats = []
        self.bot.uptime = time.time()
        if self.bot.setup:
            return
        try:
            self.bot.load_extension("Cogs.music")
        except:
            stats.append(("\U000026a0", "failed to load the music module"))
        prefixes = await self.bot.get_cog("settings").db.fetchall("SELECT guild_id, prefix FROM guild_configs")
        for gid, pref in prefixes:
            self.bot.guild_prefixes[gid] = pref
        bans = await self.bot.db.fetchall("SELECT * FROM bans")
        for i in bans:
            self.bot.bans[i[0]] = i[1]
        del bans
        # first, cache the role states.
        states = await self.bot.db.fetchall("SELECT * FROM roles")
        for gid, editor, muted, moderator, manager, streamer in states:
            self.bot.guild_role_states[gid] = {"editor": editor, "muted": muted, "moderator": moderator, "manager": manager,
                                            "streamer": streamer}

        # next, cache the module states from existing data.
        states = await self.bot.db.fetchall("SELECT * FROM module_states")
        for gid, mod, quotes, giveaway, automod, modlogs, community, fun, music, autoresponder, events, currency, modmail, basics, commands, tags, _, twitch_intergration, highlight in states:
            self.bot.guild_module_states[gid] = {"moderation": bool(mod), "quotes": bool(quotes), "automod": bool(automod), "modlogs": bool(modlogs),
                                            "community": bool(community), "fun": bool(fun), "music": bool(music), "autoresponder": bool(autoresponder),
                                            "events": bool(events), "currency": bool(currency), "giveaway": bool(giveaway), "misc": int(basics),
                                            "modmail": bool(modmail), "basics": bool(basics), "commands": bool(commands),
                                            "tags": bool(tags), "twitch": bool(twitch_intergration), "highlight": highlight}
        for vals in await self.bot.db.fetchall("SELECT * FROM timers"):
            self.bot._custom_timers.append(vals)
        # next, build the tables for the guilds joined during downtime (if any).
        for guild in self.bot.guilds:
            if guild.id not in self.bot.guild_prefixes:
                # all the cogs have their own on_guild_join method for creating new database rows.
                print("dispatching on_guild_join for server: "+str(guild.name))
                self.bot.dispatch("guild_join", guild, False) # im assuming if the prefix isnt there that nothing is there
                self.bot.guild_prefixes[guild.id] = "!"
            if guild.id not in self.bot.guild_module_states:
                self.bot.guild_module_states[guild.id] = {"moderation": False, "quotes": False, "automod": False,
                                                          "modlogs": False,
                                                          "community": False, "fun": False, "music": False,
                                                          "autoresponder": False, "misc": False,
                                                          "events": False, "currency": False, "giveaway": False,
                                                     "modmail": False, "basics": False, "commands": False, "tags": False,
                                                     "twitch": False, "highlight": False}
                await self.bot.db.execute("INSERT INTO module_states VALUES (?,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)",
                                          guild.id)
            if guild.id not in self.bot.guild_role_states:
                self.bot.guild_role_states[guild.id] = {"editor": 0, "muted": 0, "manager": 0, "moderator": 0, "streamer": 0}
                await self.bot.db.execute("INSERT INTO roles VALUES (?,0,0,0,0,0)", guild.id)
        self.bot.setup = True
        print(f"{':'.join(time.strftime('%H %M %S').split())} cache built.")
        self.bot.dispatch("currency_ready")
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
        guild = member.guild
        db = self.bot.db
        if silence:
            return
        roles = await db.fetchall("SELECT role_id FROM role_auto_assign WHERE guild_id IS ?", guild.id)
        if not roles:
            return
        robj = []
        for role in roles:
            v = guild.get_role(role)
            if not v:
                continue
            robj.append(v)
            del v
        await member.add_roles(*robj)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild, pres=True):
        await self.bot.db.execute("INSERT INTO module_states VALUES (?, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)", guild.id)
        await self.bot.db.execute("INSERT INTO roles VALUES (?, 0, 0, 0, 0, 0)", guild.id)
        self.bot.guild_prefixes[guild.id] = "!" if self.bot.run_bot != "BOB_ALPHA" else "]"
        self.bot.guild_module_states[guild.id] = {"moderation": True, "quotes": True, "automod": True,
                                                          "modlogs": True,
                                                          "community": True, "fun": True, "music": True,
                                                          "autoresponder": True, "misc": True,
                                                          "events": True, "currency": True, "giveaway": True,
                                                     "modmail": True, "basics": True, "commands": True, "tags": True,
                                                     "twitch": True, "highlight": True}
        fmt = f"**__Guild Joined__**\nname: {guild.name}\nid: {guild.id}\nowner: {guild.owner}\n\nMembers: {len(guild.members)}"
        e = commands.Embed(description=fmt, color=discord.Color.teal())
        await self.bot.get_channel(662176688150675476).send(embed=e)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        del self.bot.guild_prefixes[guild.id]
        del self.bot.guild_module_states[guild.id]
        await self.bot.db.execute("DELETE FROM roles WHERE guild_id IS ?", guild.id)
        await self.bot.db.execute("DELETE FROM module_states WHERE guild_id IS ?", guild.id)
        fmt = f"**__Guild Left__**\nname: {guild.name}\nid: {guild.id}\nowner: {guild.owner}\n\nMembers: {len(guild.members)}"
        e = commands.Embed(description=fmt, color=commands.Color.red())
        await self.bot.get_channel(662176688150675476).send(embed=e)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if after.bot:
            return
        if isinstance(after.activity, discord.Streaming) or isinstance(before.activity, discord.Streaming):
            v = self.bot.get_cog("settings").stream_cache.get(after.guild.id)
            if v is None:
                return
            AS, ACS = v.values()
            if not AS or not ACS:
                return
            c = self.bot.get_channel(ACS)  # type: discord.TextChannel
            if c is None:
                return
            if not isinstance(after.activity, discord.Streaming) and isinstance(before.activity, discord.Streaming):
                msgid = self.bot.streaming_messages.get(f"{after.id}-{after.guild.id}", None)
                if msgid is not None:
                    v = await c.fetch_message(msgid)
                    try:
                        await v.delete()
                    except:
                        pass
                    del self.bot.streaming_messages[f"{after.id}-{after.guild.id}"]
            elif after.activity == discord.Streaming:
                print(after.activity.assets)
                e = discord.Embed(title="Stream Alert!")
                e.set_author(name=str(after), icon_url=after.avatar_url)
                e.description = f"{after} is now streaming {after.activity.details} over [here!]({after.activity.url})"
                e.add_field(name="Title", value=after.activity.name)
                e.add_field(name="Twitch name", value=after.activity.twitch_name)
                m = await c.send(embed=e)
                self.bot.streaming_messages[f"{after.id}-{after.guild.id}"] = m.id
