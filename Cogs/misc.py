import asyncio
import calendar
import datetime
import io
import os
import random
import time
import typing
import uuid

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont
from discord.ext.commands import cooldown, BucketType

import runtimeinfo
from utils import btime, db, commands
from utils.checks import *
from utils.paginator import FieldPages


def setup(bots: commands.Bot):
    bots.add_cog(misc(bots))

def cooler():
    return cooldown(3, 5, BucketType.user)


async def send_message(msg, user, messagable, embed=None, mention=True):
    if mention:
        msg = user.mention + " --> " + msg
    await messagable.send(msg, embed=embed)

class misc(commands.Cog):
    category = "misc"
    def __init__(self, bot):
        self.bot = bot
        self.remindersdb = db.Database("reminders")
        self._lc = 0
        self._fc = 0
        self.latest_xkcd = 2225

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.remindersdb.execute("DELETE FROM reminders WHERE guild_id IS ?", guild.id)

    @commands.group()
    @cooler()
    @check_module('fun')
    async def xkcd(self, ctx, num_or_latest: typing.Union[int, str]=None):
        """
        some good ol' xkcd webcomics
        """
        num = num_or_latest
        if num is None:
            num = f"/{random.randint(1, 2225)}"
        elif isinstance(num, str):
            if num in ['latest', 'newest', 'l', 'n']:
                num = ""
            else:
                return await ctx.send("psst, the (optional) argument needs to be a number, or 'latest'/'l'")
        else:
            if num > self.latest_xkcd:
                return await ctx.send(f"hey, that one doesnt exist! try `{ctx.prefix}xkcd latest`")
            num = f"/{num}"
        async with self.bot.session.get(f"https://xkcd.com{num}/info.0.json") as r:
            resp = await r.json()
            if not num:
                self.latest_xkcd = resp['num']
            e = commands.Embed(name=resp['safe_title' if ctx.channel.is_nsfw() else "title"], description=resp['alt'], color=0x36393E)
            e.set_footer(text=f"#{resp['num']}  • {resp['month']}/{resp['day']}/{resp['year']}")
            e.set_image(url=resp['img'])
            await ctx.send(embed=e)

    @commands.command()
    @cooler()
    @check_module('fun')
    async def dadjoke(self, ctx):
        """
        terrible jokes, anyone?
        """ 
        async with aiohttp.ClientSession() as session:
            resp = await session.get("https://icanhazdadjoke.com", headers={"Accept": "text/plain"})
            await ctx.send((await resp.content.read()).decode("utf-8 "))

    @commands.command()
    @check_admin()
    async def setup(self, ctx: commands.Context):
        """
        a command to simplify the setup progress for bob :)
        requires server admin.
        """
        if not ctx.guild.me.guild_permissions.manage_roles and not ctx.guild.me.guild_permissions.administrator:
            await ctx.send("so uhhhh. i dont have the `manage roles` permission. I work with roles for permissions, so i kinda need that"
                           ". head on over to server settings > roles > BOB to give me that permission, then try this command again. :)")
            return
        await ctx.send("first thing: roles. im gonna ask you for some roles. if you already have them in your server, "
                       f"reply to the message by @pinging the role or with the role id. if not, reply with `none`, you can assign roles later using the `{ctx.prefix}role` command.")
        roles = {"Bot Editor": None, "Muted": None, "Community Manager": None, "Moderator": None, "Streamer": None}
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        for r in roles:
            await ctx.send(f"role: `{r}` (timeout: 1 minute)")
            try:
                m = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("timeout reached. aborting setup command")
                return
            if m.content.strip().lower() == "none":
                v = await ctx.guild.create_role(name=r, reason="Bot Setup")
                roles[r] = v.id
                await ctx.send(f"creating new `{r}` role")
            else:
                try:
                    role = await commands.RoleConverter().convert(ctx, m.content)
                    roles[r] = role.id
                except commands.CommandError:
                    await ctx.send("thats not a role! (skipping)")
        msc_cfg = {"mod_logs_channel": 0, "automod_channel": 0}
        await ctx.send("alrighty, that's all the roles. next up: channel configs. reply with a channel mention, or `none` (timeout: 30 seconds)")
        await ctx.send("first channel: modlogs")
        try:
            m = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send("timeout reached. aborting setup command.")
        else:
            if m.content.strip().lower() != "none":
                try:
                    channel = await commands.TextChannelConverter().convert(ctx, m.content)
                except commands.CommandError:
                    await ctx.send("that's not a channel! (skipping)")
                else:
                    msc_cfg['mod_logs_channel'] = channel.id
        await ctx.send("alrighty, next up: automod logs channel. (timeout: 30)")
        try:
            m = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send("timeout reached. aborting setup command.")
        else:
            if m.content.strip().lower() != "none":
                try:
                    channel = await commands.TextChannelConverter().convert(ctx, m.content)
                except commands.CommandError:
                    return await ctx.send("that's not a channel! (skipping)")
                else:
                    msc_cfg['automod_channel'] = channel.id
        if not await ctx.ask("that's all for channels. quick question: do you want to change the server prefix?"):
            await ctx.send("keeping current server prefix of "+self.bot.guild_prefixes[ctx.guild.id])
            pref = self.bot.guild_prefixes[ctx.guild.id]
        else:
            pref = await commands.clean_content().convert(ctx, await ctx.ask("ok, what should the server prefix be?", return_bool=False))
            await self.bot.get_cog("settings").db.execute("UPDATE guild_configs VALUES SET prefix=? WHERE guild_id IS ?", pref, ctx.guild.id)
            self.bot.guild_prefixes[ctx.guild.id] = pref
            await ctx.send(f"the prefix is now `{pref}")
        m = await ctx.send("that's it for setup! saving your data now...")
        await self.bot.db.execute("UPDATE roles SET editor=?, streamer=?, muted=?, moderator=?, manager=? WHERE guild_id IS ?",
                                  roles['Bot Editor'], roles['Streamer'], roles['Muted'], roles['Moderator'], roles['Community Manager'], ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id] = {"moderator": roles['Mod']}
        await self.bot.get_cog("_modlogs").db.execute("UPDATE modlogs SET channel=? WHERE guild_id IS ?", msc_cfg['mod_logs_channel'], ctx.guild.id)
        await self.bot.get_cog("automodCog").db.execute("UPDATE automod_config SET enabled=? WHERE guild_id IS ?", msc_cfg['automod_channel'], ctx.guild.id)
        self.bot.automod_states[ctx.guild.id]['channel'] = msc_cfg['automod_channel']
        await m.edit(content=f"Data saved! remember to look at `{pref}modules`, `{pref}logs`, and `{pref}help` !")

    @commands.command()
    @check_module("basics")
    async def streams(self, ctx, *, user: typing.Union[commands.Member, str]=None):
        if user is None:
            members = [x for x in ctx.guild.members if isinstance(x.activity, commands.Streaming) and not x.bot]
            matches = []
        elif isinstance(user, str):
            import difflib
            matches = await self.bot.loop.run_in_executor(None, difflib.get_close_matches, user, [str(x) for x in ctx.guild.members if isinstance(x.activity, commands.Streaming) and not x.bot], 10)
            members = []
        else:
            if isinstance(user.activity, commands.Streaming):
                r = f"↱ {user}\n⤷ `{user.activity.details}`\n   twitch name: {user.activity.twitch_name}\n   " \
                    f"link: [here]({user.activity.url} {user.activity.twitch_name})"
                e = discord.Embed(description=r)
                return await ctx.send(embed=e)
            else:
                return await ctx.send(f"{user} isn't streaming!")
        for i in matches:
            members.append(ctx.guild.get_member_named(i))
        e = []
        for m in members:
            e.append(("\u200b", f"↱ {m}\n⤷   `{m.activity.details}`\n   twitch name: {m.activity.twitch_name}\n   "
                                f"link: [here]({m.activity.url})"))
        await ctx.paginate_fields(e, per_page=4)

    @commands.command(aliases=['avy'])
    @check_module('misc')
    @cooler()
    async def avatar(self, ctx, target: discord.User=None):
        """
        sends a users avatar as a png or a gif
        """
        target = target or ctx.author #type: commands.Member
        e = commands.Embed(color=commands.Color.teal())
        e.set_image(url=(target.avatar_url_as(format="png") if not target.is_avatar_animated() else target.avatar_url_as(format="gif")))
        await ctx.send(embed=e)

    @commands.command(aliases=["lc", "source"])
    @check_module('basics')
    @cooler()
    async def linecount(self, ctx):
        """
        shows the amount of lines that create bob!
        """
        if not self._lc:
            await self.lc()
        await ctx.send(embed=ctx.embed_invis(description=f"BOB is compiled of {self._lc} lines spead over {self._fc} files! you can view the source [here!](https://github.com/IAmTomahawkx/bob/tree/master)"))

    async def lc(self):
        amo = 0
        fileamo = 0
        dirs = ["Cogs", "libraries", "utils"]
        files = ["main.py", "randomstuff.py", "runtimeinfo.py"]
        indir = os.path.dirname(os.path.dirname(__file__))
        for dir in dirs:
            for name in os.listdir(os.path.join(indir,dir)):
                if name == "__pycache__": continue
                fileamo += 1
                name = os.path.join(indir, dir, name)
                with open(name, encoding="utf-8") as f:
                    amo += len(f.read().split('\n'))
        for file in files:
            if file == "__pycache__": continue
            fileamo += 1
            with open(file) as f:
                amo += len(f.read().split("\n"))
        amo = list(str(amo))
        amo.insert(1, ",")
        self._lc = "".join(amo)
        self._fc = fileamo

    @commands.command(usage="<when> [reminder]", aliases=['reminder', 'remind'])
    @check_module("misc")
    @cooler()
    async def remindme(self, ctx, *, when: btime.UserFriendlyTime(commands.clean_content(), default="\u2026")):
        """Reminds you of something after a certain amount of time.
        The input can be any direct date (e.g. YYYY-MM-DD) or a human
        readable offset. Examples:
        - "next thursday at 3pm do something funny"
        - "do the dishes tomorrow"
        - "in 3 days do the thing"
        - "2d unmute someone"
        Times are in UTC.
        """
        delta = btime.human_timedelta(when.dt, source=datetime.datetime.utcnow())
        id = str(uuid.uuid4())
        await self.remindersdb.execute("INSERT INTO reminders"
                                  " VALUES (?,?,?,?,?,?,?)", ctx.guild.id, ctx.channel.id,
                                        when.arg, calendar.timegm(when.dt.timetuple()), ctx.message.jump_url, ctx.author.id, id)
        await self.bot.db.commit()
        await ctx.send(f"{ctx.author.mention} --> reminding you in {delta}: {when.arg}")
        self.bot.ws

    async def pred(ctx):
        return await ctx.bot.is_owner(ctx.author)

    @commands.command(hidden=True)
    @commands.is_owner()
    @commands.help_check(pred)
    async def say(self, ctx, *, msg):
        """
        go away
        """
        await ctx.send(msg)
        try:
            await ctx.message.delete()
        except:
            pass

    @commands.command("afk")
    @check_module("misc")
    @cooler()
    async def set_afk(self, ctx, *, params: commands.clean_content):
        """
        sets an AFK state. this will alert others when they mention you.
        """
        exists = await self.bot.db.fetch("SELECT * FROM afks WHERE guild_id IS ? AND user_id IS ?", ctx.guild.id, ctx.author.id)
        if exists:
            await self.bot.db.execute("UPDATE afks SET reason = ? WHERE guild_id IS ? AND user_id IS ?",
                                      params, ctx.guild.id, ctx.author.id)
        else:
            await self.bot.db.execute("INSERT INTO afks VALUES (?, ?, ?)",
                                      ctx.guild.id, ctx.author.id, params if params else "No Reason")
        if params:
            await send_message(f"set your afk to ``{params}``", ctx.author, ctx.channel)
        else:
            await send_message("set your afk.", ctx.author, ctx.channel)

    @commands.command(aliases=["bug"], usage="<explanation of bug/idea>")
    @commands.cooldown(3, 600)
    async def idea(self, ctx, *, msg: str = None):
        """
        submit a bug report / idea submission
        there is a cooldown of 3 uses per 10 minutes.
        cooldown is shared between !bug and !idea
        """
        if not msg:
            return
        db = self.bot.glob_db
        if await (await db.execute("SELECT user_id FROM IDEAS_banned WHERE user_id IS ?", (ctx.author.id,))).fetchone():
            await ctx.send(f"{ctx.author.mention} --> you've been banned from idea requests/bug reports!")
            return # user is banned from ideas/ bug reports
        if msg in await db.fetchall("SELECT msg FROM IDEAS WHERE user_id IS ? AND type IS ?", ctx.author.id, ctx.invoked_with):
            # dont let the user know that it has been blocked, in case they are spamming
            await ctx.send(f"{ctx.author.mention} --> your {ctx.invoked_with} was shot into the clouds!")
            return
        await db.execute("INSERT INTO IDEAS VALUES (?, ?, ?, ?)", (ctx.author.id,
                         ctx.invoked_with, msg, ctx.message.id))
        e = discord.Embed()
        e.timestamp = datetime.datetime.utcnow()
        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        e.set_footer(text="userid: "+str(ctx.author.id))
        if ctx.invoked_with == "idea":
            e.title = "A New Idea!"
            e.colour = discord.Color.teal()
            e.description = "idea id: "+str(ctx.message.id)
            e.add_field(name="the idea", value=msg)
            v = self.bot.get_guild(604085864514977813).get_channel(604928682674618401)
            m = await v.send(embed=e)
            await ctx.send("your idea has been shot into the clouds! it can be seen/ voted for on the BOB discord server!")
        elif ctx.invoked_with == "bug":
            e.title = "A New Bug?"
            e.colour = discord.Color.red()
            e.description = "bug id: "+str(ctx.message.id)
            e.add_field(name="the bug", value=msg)
            v = self.bot.get_guild(604085864514977813).get_channel(604928708414799883)
            m = await v.send(embed=e)
            await ctx.send("your bug report has been shot into the clouds! it can be seen on the BOB discord server!")
        await m.add_reaction("✅")
        await m.add_reaction("❎")

    @commands.command()
    @cooler()
    @check_module('misc')
    async def think(self, ctx):
        """
        the large think
        """
        await ctx.send("""<:rooThink_0:612835870470438923><:rooThink_1:612835870600331265><:rooThink_2:612835870512513034><:rooThink_3:612835870508318740><:rooThink_4:612835870739005440><:rooThink_5:612835870436884482><:rooThink_6:612835870596399135>
<:rooThink_7:612835870961303554><:rooThink_8:612835870818435072><:rooThink_9:612835870734680074><:rooThink_10:612835870948589578><:rooThink_11:612835871086870580><:rooThink_12:612835870625759243><:rooThink_13:612835870575296534>
<:rooThink_14:612835870654857221><:rooThink_15:612835870806114330><:rooThink_16:612835871166824460><:rooThink_17:612835870831149057><:rooThink_18:612835870743199745><:rooThink_19:612835870529290241><:rooThink_20:612835870969561089>
<:rooThink_21:612835870441209891><:rooThink_22:612835870445404173><:rooThink_23:612835870487085082><:rooThink_24:612835870562844693><:rooThink_25:612835870747394071><:rooThink_26:612835871145852928><:rooThink_27:612835870910709771>
<:rooThink_28:612835873553383456><:rooThink_29:612835870915035136><:rooThink_30:612835871191728129><:rooThink_31:612835870969692191><:rooThink_32:612835871112298497><:rooThink_33:612835870663245826><:rooThink_34:612835870978080805>
<:rooThink_35:612835871183470592><:rooThink_36:612835871070355466><:rooThink_37:612835870776492040><:rooThink_38:612835870621433870><:rooThink_39:612835870793269258><:rooThink_40:612835870529028096><:rooThink_41:612835870575296512>
<:rooThink_42:612835870583816197><:rooThink_43:612835870508318770><:rooThink_44:612835871061704704><:rooThink_45:612835870260854790><:rooThink_46:612835870998790167><:rooThink_47:612835870600331304><:rooThink_48:612835870931943424>""")

    @commands.command()
    @cooler()
    async def uptime(self, ctx):
        """
        gets the amount of time the bot has been online for
        """
        import time
        up = time.time() - self.bot.uptime
        if up < 0:
            return
        mins = 0
        hours = 0
        days = 0
        while up > 60:
            mins += 1
            up -= 60
        while mins >= 60:
            hours += 1
            mins -= 60
        while hours >= 24:
            days += 1
            hours -= 24
        e = discord.Embed()
        e.colour = discord.Color.teal()
        e.set_footer(
            text=f"Shard {str(ctx.guild.shard_id)} | {'Hesland' if not 'alpha' in self.bot.run_bot.lower() else 'Exland'} | system start {time.ctime(self.bot.STARTED_TIME)}")
        e.add_field(name="uptime:", value="{0} days, {1} hours, and {2} minutes".format(days, hours, mins))
        await ctx.send(embed=e)

    @commands.command()
    @cooler()
    async def ping(self, ctx: commands.Context):
        """ Pong! """
        before = time.monotonic()
        message = await ctx.send("Pong")
        ping = (time.monotonic() - before) * 1000
        await message.edit(content=f"\U0001f3d3 Pong   |   {int(ping)}ms")
        await async_ping(ctx, ping)
        await message.delete()

    @commands.command(hidden=True)
    @check_admin()
    async def leave_guild(self, ctx: commands.Context):
        """
        makes the bot leave your guild.
        requires the `Administrator` permission (note, this is not a role)
        """
        await ctx.send("Hey there! Are you sure you want me to leave?")
        async def predicate(data):
            return ctx.author == data.author and ctx.channel == data.channel
        try:
            msg = await self.bot.wait_for("message", check=predicate, timeout=30)
        except Exception:
            await ctx.send("Aborting leave command")
            return
        if "yes" in msg.content.lower():
            v = await ctx.send("alright then. starting cleanup")
        else:
            await ctx.send("aborting")
            return
        print(f"leaving guild: {ctx.guild.name} | {ctx.guild.id}\ninitiated by user {ctx.author} | {ctx.author.id}")
        await asyncio.sleep(0.4)
        await v.edit(content="cleaning database")
        await asyncio.sleep(0.6)
        await v.edit(content="purging roles")
        v = await self.bot.db.execute("SELECT editor FROM roles WHERE guild_id IS ?", (ctx.guild.id,))
        r = await v.fetchone()
        await ctx.guild.get_role(r[0]).delete()
        await v.edit(content="removed bot editor role\ncleanup complete\nleaving")
        await ctx.guild.leave()

    @commands.command(aliases=['about', 'botinfo'])
    @cooler()
    async def info(self, ctx):
        """
        provides info about the bot
        """
        if not self._lc:
            await self.lc()
        e = discord.Embed(color=discord.Color.teal())
        e.set_footer(text=f"Shard {ctx.guild.shard_id or 0} | {self.bot.settings['server']} | system start {time.ctime(self.bot.STARTED_TIME)}")
        e.timestamp = datetime.datetime.utcnow()
        rep = f"running {self.bot.settings['run_display_name']} | version {self.bot.version} on server {self.bot.settings['server']}"
        e.add_field(name="bot info", value=rep)
        e.add_field(name="line count", value=f"BOB is compiled of {self._lc} lines spead over {self._fc} files!")
        e.add_field(name="Author", value="IAmTomahawkx#1000")
        e.add_field(name="need help?", value="[super active support server!](https://discord.gg/VKp6zrs)\nalso, there's the help command")
        await ctx.send(embed=e)

    @commands.command()
    @cooler()
    async def invite(self, ctx):
        """
        invite me to your server!
        """
        e = discord.Embed(color=discord.Color.teal())
        e.set_author(name="You can invite me here!", url="https://discordapp.com/api/oauth2/authorize?client_id=587482154938794028&permissions=2147483127&scope=bot",)
        await ctx.send(embed=e)

    @commands.command()
    @check_module('misc')
    @check_editor()
    @cooler()
    async def nick(self, ctx, *, name: str):
        """
        a quick way to change bobs nickname
        """
        try:
            await ctx.guild.me.edit(nick=name)
        except (discord.HTTPException, discord.Forbidden):
            await ctx.send("missing permissions to change my nickname!")
        else:
            await ctx.send("Updated name to "+name)

    @commands.command()
    @check_module("misc")
    @cooler()
    async def changelog(self, ctx):
        """
        a list of bob's evolutions
        """
        desc = f"Most Recent Change:```\n{self.bot.most_recent_change}\n```"
        v = FieldPages(ctx, entries=[v for v in reversed([tuple(v) for v in self.bot.changelog.items()])], description=desc,
                       title=f"Version: {self.bot.version}", embed_color=discord.Color.dark_magenta(), per_page=3, delete_after=False)
        await v.paginate()

    @commands.command("profile", usage="[target]", enabled=False,hidden=True)
    @check_module("currency")
    @commands.help_check(lambda c: False)
    @commands.cooldown(1, 15, commands.BucketType.member)
    async def profile_get(self, ctx: commands.Context, target: discord.Member = None):
        """
        gets your server profile card
        """
        target = target or ctx.author
        points, total_msg, total_warn = self.bot.get_cog("points").cache[target.guild.id][target.id].values()
        await aio_create_profile_card(ctx, target, points, total_msg, total_warn)
        return
        e = discord.Embed(timestamp=datetime.datetime.utcnow(), color=discord.Color.teal())
        e.set_thumbnail(url=ctx.author.avatar_url)
        e.title = "**your profile**" if target == ctx.author else "**profile for {0.display_name}**".format(target)
        e.set_author(name=str(target.name), icon_url=target.avatar_url)
        e.set_footer(text="note: stats are since the bot joined")
        e.add_field(name="*Warnings*", value=str(total_warn))
        if points is not None:
            e.add_field(name="*Points*", value=str(points))
        e.add_field(name="*total server messages*", value=str(total_msg))
        e.add_field(name="*joined at*", value=ctx.author.joined_at)
        await ctx.send(embed=e)

avy_bg = os.path.join(runtimeinfo.INSTALL_DIR, "data", "photos", "avy_bg3.png")

async def aio_create_profile_card(ctx, user, points, total_msg, warnings):
    await ctx.trigger_typing()
    pfp = Image.open(io.BytesIO(await user.avatar_url_as(format="png", size=256).read()))
    loop = asyncio.get_running_loop()
    file = await loop.run_in_executor(None, create_profile_card, pfp, str(user), points, total_msg, warnings)
    await ctx.send(file=file)

def create_profile_card(pfp: Image.Image, name, points, total_msg, warnings):
    bg = Image.open(avy_bg, 'r')
    img_w, img_h = pfp.size
    bg_w, bg_h = bg.size
    pfp.resize((img_w*2, img_h*2))
    pfp, mask = _add_corners(pfp) # this aint working and idk why
    pfp = pfp.copy()
    bg.paste(pfp, (50, 50), mask)
    add_text(bg, name, points, warnings, total_msg)
    buf = io.BytesIO()
    bg.save(buf, format='png')
    buf.seek(0)
    bg.close()
    return discord.File(buf, filename="pfp.png")

def _add_corners(image, rad=130):
    circle = Image.new("L", (rad * 2, rad * 2))
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
    alpha = Image.new("L", image.size, 255)
    w, h = image.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    image.putalpha(alpha)
    return image, alpha

def add_text(img, name, points, warns, tot):
    fnt = ImageFont.truetype(os.path.join(runtimeinfo.INSTALL_DIR, "data", "Dreamstar.otf"), 75)
    fnt2 = ImageFont.truetype(os.path.join(runtimeinfo.INSTALL_DIR, "data", "grime.ttf"), 100)
    d = ImageDraw.Draw(img)
    f = f"""
{points} Points | {warns} Warnings | {tot} Total Messages
    """"".strip()
    d.text((50, 350), f, font=fnt, fill=(175, 161, 18))
    d.text((300, 130), name, font=fnt2, fill=(23, 201, 71))

import matplotlib.figure as plt

async def async_ping(ctx, delay):
    file = await ctx.bot.loop.run_in_executor(None, plot_ping, ctx.bot, delay)
    return await ctx.send(file=file)

def plot_ping(bot, delay):
    if not bot.pings:
        raise commands.CommandError("No pings available.")

    fig = plt.Figure()
    ax = fig.subplots()

    pings = []
    times = []
    total_ping = 0
    for time, latency in bot.pings:
        if latency == float("nan"):
            continue
        pings.append(round(latency, 0))
        times.append(f"{time.hour if time.hour > 9 else f'0{time.hour}'}-{time.minute}")
        total_ping += latency

    def hilo(numbers):
        highest = [index for index, val in enumerate(numbers) if val == max(numbers)]
        lowest = [index for index, val in enumerate(numbers) if val == min(numbers)]
        return highest, lowest

    highest_ping, lowest_ping = hilo(pings)

    average_ping = round(sum([ping if str(ping) != "nan" else 0 for _, ping in bot.pings ]) / len(bot.pings), 1)
    ax.plot(times, pings, markersize=0.0, linewidth=0.5, c="purple", alpha=1)
    ax.plot(times, pings, markevery=lowest_ping, c='lime', linewidth=0.0, marker='o', markersize=4)
    ax.plot(times, pings, markevery=highest_ping, c='red', linewidth=0.0, marker='o', markersize=4)
    ax.fill_between(range(0, len(pings)), [0 for _ in pings], pings, facecolor="purple", alpha=0.2)
    ax.text(1, 1, f"Current gateway ping: {round(bot.latency * 1000, 1)} ms\nAverage Ping: {average_ping} ms\nMessage ping: {round(delay)}ms")
    ax.set(ylabel="Ping (MS)", xlabel="the last hour (UTC)")

    ax.tick_params(
        axis='x',
        which='major',
        bottom=False,
        top=False,
        labelbottom=False)

    image = io.BytesIO()
    fig.savefig(image)
    image.seek(0)

    return discord.File(image, filename="ping.png")