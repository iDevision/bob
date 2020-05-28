import asyncio
import calendar
import datetime
import io
import os
import random
import time
import typing
import uuid

import discord
from discord.ext.commands import cooldown, BucketType

from utils import btime, db, commands
from utils.checks import *
from utils.paginator import FieldPages


def setup(bots: commands.Bot):
    bots.add_cog(misc(bots))

def cooler():
    return cooldown(3, 5, BucketType.user)

class misc(commands.Cog):
    category = "misc"
    def __init__(self, bot):
        self.bot = bot
        self._lc = 0
        self._fc = 0

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.bot.db.execute("DELETE FROM reminders WHERE guild_id = $1", guild.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: commands.Member, after: commands.Member):
        if isinstance(before.status, commands.Streaming) or not isinstance(after.status, commands.Streaming):
            return

        if after.guild.id not in self.bot.streamers or after.id not in self.bot.streamers[after.guild.id]['ids']:
            return

        channel = after.guild.get_channel(self.bot.streamers[after.guild.id]['channel'])
        if channel is None:
            return

        if not self.bot.streamers[after.guild.id]['message']:
            return

        await channel.send(self.bot.streamers[after.guild.id]['message'].replace("$url", after.status.url).replace(
            "$user", str(after)).replace("$title", after.status.name).replace("$game", after.status.game))

    @commands.group()
    @check_module("basics")
    @check_manager()
    async def streaming(self, ctx):
        """
        controls the streaming announcer. see `{ctx.prefix}help streaming` for usage and subcommands
        """
        pass

    @streaming.command("add")
    @check_manager()
    @check_module("basics")
    async def strm_add_usr(self, ctx, user: commands.Member):
        """
        tells the announcer to send a message when the target person goes live
        requires the `Community Manager` role or higher
        """
        await self.bot.pg.execute("INSERT INTO stream_announcer VALUES ($1,$2,null,null) ON CONFLICT (guild_id) DO UPDATE SET "
                                  "users = ARRAY_CAT(stream_announcer.users, $2) WHERE stream_announcer.guild_id = $1", ctx.guild.id, [user.id])
        if ctx.guild.id in self.bot.streamers:
            self.bot.streamers[ctx.guild.id]['ids'].append(user.id)
        else:
            self.bot.streamers[ctx.guild.id] = {"ids": [user.id], "channel": None, "message": ""}
        await ctx.send(f"I will now announce when {user} goes live. Ensure that a message has been set, and that a channel has been set.")

    @streaming.command("channel")
    @check_module("basics")
    @check_manager()
    async def strm_chnl(self, ctx, channel: commands.TextChannel):
        """
        sets the channel for the announcer to announce to.
        """
        if ctx.guild.id in self.bot.streamers:
            self.bot.streamers[ctx.guild.id]['channel'] = channel.id
        else:
            self.bot.streamers[ctx.guild.id] = {"ids": [], "channel": channel.id, "message": ""}

        await self.bot.pg.execute("INSERT INTO stream_announcer VALUES ($1,$3,$2,null) ON CONFLICT (guild_id) DO UPDATE SET "
                                  "channel = $2 WHERE stream_announcer.guild_id = $1", ctx.guild.id, channel.id, [])
        await ctx.send(f"set the announcer channel to {channel.mention}")

    @streaming.command("message", aliases=['msg'])
    @check_module("basics")
    @check_manager()
    async def strm_msg(self, ctx, *, msg):
        """
        sets the message to be sent to the announcement channel when a user goes live.
        the following parameters can be used:

        """
        await self.bot.pg.execute("INSERT INTO stream_announcer VALUES ($1,$3,null,$2) ON CONFLICT (guild_id) DO UPDATE SET "
                                  "message = $2 WHERE stream_announcer.guild_id = $1", ctx.guild.id, msg, [])
        if ctx.guild.id in self.bot.streamers:
            self.bot.streamers[ctx.guild.id]['message'] = msg
        else:
            self.bot.streamers[ctx.guild.id] = {"ids": [], "channel": None, "message": msg}

        await ctx.send("Set the announcer message")

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
        roles = {"Bot Editor": None, "Muted": None, "Community Manager": None, "Moderator": None}
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

        m = await ctx.send("that's it for setup! saving your data now...")
        await self.bot.db.execute("INSERT INTO roles VALUES ($5,$1,$2,$3,$4) ON CONFLICT (guild_id) DO UPDATE SET editor=$1, muted=$2, moderator=$3, manager=$4 WHERE guild_id = $5",
                                  roles['Bot Editor'], roles['Muted'], roles['Moderator'], roles['Community Manager'], ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id] = {"moderator": roles['Moderator'], "editor": roles['Bot Editor'], "muted": roles['Muted'], "manager": roles['Community Manager']}
        await self.bot.get_cog("_modlogs").db.execute("UPDATE modlogs SET channel=? WHERE guild_id IS ?", msc_cfg['mod_logs_channel'], ctx.guild.id)
        await self.bot.get_cog("automodCog").db.execute("UPDATE automod_config SET enabled=? WHERE guild_id IS ?", msc_cfg['automod_channel'], ctx.guild.id)
        self.bot.automod_states[ctx.guild.id]['channel'] = msc_cfg['automod_channel']
        await m.edit(content=f"Data saved! remember to look at `{ctx.prefix}modules`, `{ctx.prefix}logs`, and `{ctx.prefix}help`!")

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
    @check_module('misc')
    @cooler()
    async def linecount(self, ctx):
        """
        shows the amount of lines that create bob!
        """
        if not self._lc:
            await self.lc()
        await ctx.send(embed=ctx.embed_invis(description=f"BOB is compiled of {self._lc} lines spead over {self._fc} files! you can view the source [here!](https://github.com/IDevision/bob)"))

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
        if len(amo) == 4:
            amo.insert(1, ",")
        else:
            amo.insert(2, ",")
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
        await self.bot.pg.execute("INSERT INTO reminders"
                                  " VALUES ($1,$2,$3,$4,$5,$6)", ctx.guild.id, ctx.channel.id,
                                        when.arg, when.dt, ctx.message.jump_url, ctx.author.id)
        await ctx.send(f"{ctx.author.mention} reminding you in {delta}: {when.arg}")

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
            await ctx.send(f"set your afk to ``{params}``")
        else:
            await ctx.send("set your afk.")

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
        try:
            await ctx.message.delete()
        except:
            pass

    @commands.command()
    @cooler()
    @check_module('misc')
    async def thonk(self, ctx):
        """
        the large thonk
        """
        await ctx.send("""
<:rooThonk_0:689343585899773994><:rooThonk_1:689343584381435939><:rooThonk_2:689343578924908593><:rooThonk_3:689343526793773069><:rooThonk_4:689343528715026475><:rooThonk_5:689343536809639966><:rooThonk_6:689343537560551454>
<:rooThonk_7:689343586495496193><:rooThonk_8:689343533240680449><:rooThonk_9:689343587506323484><:rooThonk_10:689343539007848486><:rooThonk_11:689343580673671238><:rooThonk_12:689343578396295227><:rooThonk_13:689343533777289216>
<:rooThonk_14:689343576097947784><:rooThonk_15:689343577620611208><:rooThonk_16:689343576911642624><:rooThonk_17:689343526131073044><:rooThonk_18:689343536042082387><:rooThonk_19:689343510511353966><:rooThonk_20:689343575040852003>
<:rooThonk_21:689343541826289685><:rooThonk_22:689343516446556180><:rooThonk_23:689343538214862888><:rooThonk_24:689343524549820432><:rooThonk_25:689343532716130370><:rooThonk_26:689343516081389570><:rooThonk_27:689343528085749790>
<:rooThonk_28:689343541171716162><:rooThonk_29:689343540483981355><:rooThonk_30:689343517566566422><:rooThonk_31:689343575770529831><:rooThonk_32:689343582108385526><:rooThonk_33:689343509869625345><:rooThonk_34:689343529809608744>
<:rooThonk_35:689343530568646679><:rooThonk_36:689343581537697793><:rooThonk_37:689343525451464741><:rooThonk_38:689343535014477838><:rooThonk_39:689343534326874134><:rooThonk_40:689343532237979673><:rooThonk_41:689343588106108944>
<:rooThonk_42:689343583148441610><:rooThonk_43:689343585023557642><:rooThonk_44:689343527523713049><:rooThonk_45:689343539657572391><:rooThonk_46:689343579755118623><:rooThonk_47:689343583849152570><:rooThonk_48:689343535534702632>
        """)
        try:
            await ctx.message.delete()
        except:
            pass

    @commands.command()
    @cooler()
    async def uptime(self, ctx):
        """
        gets the amount of time the bot has been online for
        """
        e = discord.Embed()
        e.colour = discord.Color.teal()
        ut = self._uptime()
        e.set_footer(
            text=f"Shard {ctx.guild.shard_id or None} | {'Hesland' if not 'alpha' in self.bot.run_bot.lower() else 'Exland'}")
        e.add_field(name="uptime:", value=ut)
        await ctx.send(embed=e)

    def _uptime(self):
        return btime.human_timedelta(self.bot.uptime, suffix=False)

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
    async def why(self, ctx):
        """thanks discord"""
        await ctx.send(random.choice(["because™️ it™️ is™️ intentional™️ design™️ by™️ discord™️ ","""**Can you implement X?**

- "The technology just isn't there yet."
- "We don't have enough employees to implement this feature."
- "It's too low priority for us to even bother at this time."
- *no comment at all*

Pick one."""]))

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
        try:
            await ctx.guild.get_role(r[0]).delete()
            await v.edit(content="removed bot editor role\ncleanup complete\nleaving")
        except: pass
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
        e.set_footer(text=f"Shard {ctx.guild.shard_id or 0} | {self.bot.settings['server']} | up for {self._uptime()}")
        e.timestamp = datetime.datetime.utcnow()
        rep = f"version {self.bot.version} on server {self.bot.settings['server']}"
        e.add_field(name="stuff", value=rep)
        e.add_field(name="line count", value=f"BOB is compiled of {self._lc} lines spead over {self._fc} files!")
        e.add_field(name="Author", value="IAmTomahawkx#1000")
        e.add_field(name="need help?", value="[super active support server!](https://discord.gg/wcVHh4h)\nalso, there's the help command")
        e.set_image(url="https://cdn.discordapp.com/attachments/673280165043765258/673975787187077120/Devision.png")
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
        name = name if name != "remove" else None
        try:
            await ctx.guild.me.edit(nick=name if name != "remove" else None)
        except (discord.HTTPException, discord.Forbidden):
            await ctx.send("missing permissions to change my nickname!")
        else:
            await ctx.send("Updated nickname to "+name if name is not None else "Removed nickname")

    @commands.command()
    @check_module("misc")
    @cooler()
    async def changelog(self, ctx):
        """
        a list of bob's evolutions
        """
        desc = f"Most Recent Change:```\n{self.bot.most_recent_change}\n```"
        v = FieldPages(ctx, entries=[v for v in reversed([tuple(v) for v in self.bot.changelog.items() if v != self.bot.most_recent_change])],
                       description=desc,
                       title=f"Version: {self.bot.version}", embed_color=discord.Color.dark_magenta(), per_page=3, delete_after=False)
        await v.paginate()

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
    ax.set(ylabel="Ping (MS)", xlabel="the last hour")

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