import discord

from utils import db, commands, objects
from utils.checks import *
import re
import asyncio
import inspect
import yarl


def setup(bot):
    bot.add_cog(automodCog(bot))

PRESET_STRICT_FMT = "Profanity filter - Mute user (use default word list)\nInvites filter - Kick user\nSpam filter - " \
                      "Ban user\nMass Mentions Filter - 5 pings, Ban user\nInvites filter - mute user"
PRESET_RELAXED_FMT = "Profanity filter - delete message"

def check_configured():
    def inner(ctx):
        if ctx.guild.id not in ctx.bot.automod_states:
            raise commands.CheckFailure(f"Automod is not configured. use `{ctx.prefix}automod init` to configure automod")
        return True
    return commands.check(inner)

class AutomodLevelConverter(commands.Converter):
    def __init__(self, max_level=4):
        self.max = max_level

    async def convert(self, ctx, argument):
        argument = argument.lower()
        if argument in ("off", "0", "disable", "disabled"):
            return 0
        try:
            argument = int(argument)
        except:
            raise commands.BadArgument("Unacceptable automod argument.")
        else:
            if argument >= 1 and not ctx.guild.me.guild_permissions.manage_messages:
                raise commands.BadArgument("I need to have manage messages permissions to enable automod")

            if argument == 2 and not ctx.guild.me.guild_permissions.manage_roles:
                raise commands.BadArgument("I need to have manage roles permissions to enable level 2 automod!")

            if argument == 3 and not ctx.guild.me.guild_permissions.kick_members:
                raise commands.BadArgument("I need to have kick members permissions to enable level 3 automod!")

            if argument == 4 and not ctx.guild.me.guild_permissions.ban_members:
                raise commands.BadArgument("I need to have ban members permissions to enable level 4 automod!")

            if self.max < argument < 1:
                raise commands.BadArgument("Invalid automod level")
            return argument

class automodCog(commands.Cog):
    walk_on_help = False
    def __init__(self, bot):
        self.bot = bot
        self.states = self.bot.automod_states
        if not self.states:
            self.bot.loop.create_task(self.on_ready())

    async def cog_check(self, ctx):
        return await basic_check(ctx, "editor") and check_module("automod")

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.automod_states:
            return

        conn = await self.bot.pg.acquire()
        data = await conn.fetch("SELECT * FROM automod;")
        ignore = await conn.fetch("SELECT * FROM automod_ignore;")
        words = await conn.fetch("SELECT * FROM automod_triggers;")
        await self.bot.pg.release(conn)

        for record in data:
            self.states[record['guild_id']] = objects.AutomodLevels(record['flags'],
                                                                    record['raidmode'],
                                                                    self.bot.get_channel(record['channel']),
                                                                    record['default_wordlist'],
                                                                    None,
                                                                    record['caps_percent'])

            _words = []
            for rec in words:
                await asyncio.sleep(0)
                if rec['guild_id'] == record['guild_id'] and rec['type'] is 1:
                    _words.append(rec['word'])

            _links = []
            for rec in words:
                await asyncio.sleep(0)
                if rec['guild_id'] == record['guild_id'] and rec['type'] is 2:
                    _links.append(rec['word'])

            self.states[record['guild_id']].blacklisted_links = _links

            self.states[record['guild_id']].regex = re.compile((
                      r'(?i)'  # case insensitive
                      r'\b'  # word bound
                      r'(?:{})'  # non capturing group, to make sure that the word bound occurs before/after all words
                      r'\b'
                      ).format('|'.join(map(re.escape, _words))))

            for ignore_rec in ignore:
                await asyncio.sleep(0)
                if ignore_rec['guild_id'] == record['guild_id']:
                    if ignore_rec['type'] == 1:
                        self.states[record['guild_id']].ignored_channels.append(ignore_rec['id'])
                    else:
                        self.states[record['guild_id']].ignores_roles.append(ignore_rec['id'])


    @commands.group(invoke_without_command=True, usage="[subcommands]", walk_help=False)
    @check_configured()
    async def automod(self, ctx):
        """
        to start with automod, make sure you run `{ctx.prefix}automod init`
        be sure to look at the presets first using `{ctx.prefix}help automod preset`!
        not content with the presets? this allows you to fine tune automod to your liking!
        (do note that this can get complex in some spots)
        requires the `bot editor` role to edit anything in this category
        """
        levels = {
            0: "Off",
            1: "Delete offending message",
            2: "Delete offending message + mute the offending user",
            3: "Delete offending message + kick the user",
            4: "Delete offending message + ban the user"
        }
        state = self.states[ctx.guild.id]
        fmt = inspect.cleandoc(
            f"""
            **Automod Overview:**
            Message Spam       - {levels[state.spam]}
            Mass Mentions      - {levels[state.mass_mentions]} (Threshold: {state.mass_mentions_amount})
            Caps Protection    - {levels[state.caps]} (Threshold: {state.caps_percent}%)
            Links Protection   - {levels[state.links]}
            Invites Protection - {levels[state.invites]}
            Profanity Filter   - {levels[state.words]} (Use default word list: {'Yes' if state.default_filter else 'No'})
            """)

        emb = ctx.embed_invis(description=fmt)
        emb.add_field(name="**Blacklisted Domains**", value="\n".join(state.blacklisted_links) or "None blacklisted")
        emb.add_field(name="**Banned Words**", value="\n".join(state.bad_words) or "None blacklisted")
        await ctx.send(embed=emb)

    @automod.command()
    async def init(self, ctx):
        if ctx.guild.id in self.states:
            return await ctx.send("Automod has already been initialized for this server")

        self.states[ctx.guild.id] = state = objects.AutomodLevels.none()
        await self.bot.pg.execute("INSERT INTO automod VALUES ($1,$2,$3,$4,$5,$6);", ctx.guild.id, *state.save())
        await ctx.send("Automod has now been initialized and is ready to moderate on this server")

    @automod.command("reset")
    async def am_reset(self, ctx):
        if await ctx.ask("Are you sure you want to reset all automod values?"):
            await self.bot.pg.execute(f"DELETE FROM automod WHERE guild_id = {ctx.guild.id}; DELETE FROM automod_triggers"
                                      f" WHERE guild_id = {ctx.guild.id}; DELETE FROM automod_ignore WHERE guild_id = {ctx.guild.id}")
            self.states[ctx.guild.id] = state = objects.AutomodLevels.none()
            await self.bot.pg.execute("INSERT INTO automod VALUES ($1,$2,$3,$4,$5,$6);", ctx.guild.id, *state.save())
            await ctx.send("reset automod to defaults")

    @automod.command(hidden=True, usage="<relaxed/strict>", aliases=['presets'])
    @check_configured()
    async def preset(self, ctx, mode: str):
        mode = mode.lower()
        if mode not in ["relaxed", "strict"]:
            return await ctx.send("Invalid mode!")

        state = self.states[ctx.guild.id]
        if mode == "relaxed":
            state.raidmode_relaxed()

        elif mode == "strict":
            state.raidmode_strict()

        await self.bot.pg.execute("UPDATE automod SET flags = $1, raidmode = $2, channel = $3, caps_percent=$4, default_wordlist = $5 WHERE guild_id = $6;", *state.save(), ctx.guild.id)
        await ctx.send(f"automod has now been set to the following:\n{PRESET_RELAXED_FMT if mode == 'relaxed' else PRESET_STRICT_FMT}")

    @automod.group(invoke_without_command=True, usage="[channel/'remove']")
    @check_configured()
    async def channel(self, ctx, channel: discord.TextChannel=None):
        """
        set the channel to output automod logs to. type `reset` to remove the automod log channel.
        """
        if channel:
            await self.bot.pg.execute("UPDATE automod SET channel = $1 WHERE guild_id = $2", channel.id, ctx.guild.id)
            self.states[ctx.guild.id].channel = channel.id
            await ctx.send(f"{ctx.author.mention} --> set automod channel to {channel.mention}")
        else:
            c = self.states[ctx.guild.id]
            c = self.bot.get_channel(c.channel)
            if not c:
                return await ctx.send(f"{ctx.author.mention} --> invalid automod channel!")
            await ctx.send(f"{ctx.author.mention} --> automod output channel: {c.mention}")


    @channel.command("reset", usage="(no parameters)", aliases=['remove'])
    @check_configured()
    async def am_c_reset(self, ctx):
        """
        removes the automod logging channel
        """
        await self.bot.pg.execute("UPDATE automod SET channel = null WHERE guild_id IS $1", ctx.guild.id)
        self.states[ctx.guild.id].channel = None
        await ctx.send(f"{ctx.author.mention} --> reset automod channel")

    @automod.command("spam", usage="[level]")
    @check_configured()
    async def am_ms(self, ctx, level: AutomodLevelConverter = None):
        """
        message spam automod protects against users spamming a channel.
        levels are as follows:
        `1` - purge the messages
        `2` - purge the messages, mute the user
        `3` - purge the messages, kick the user
        `4` - purge the messages, ban the user
        or `off` to disable spam protection
        """
        if level is None:
            pun = self.states[ctx.guild.id].spam
            e = discord.Embed(name="Currently Enabled: ")
            e.description = "True" if pun != 0 else "False"
            e.add_field(name="punishment", value=str(pun))
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].spam = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Spam punishment has been set to {'off' if level == 0 else level}")

    @automod.group("profanity", invoke_without_command=True, usage="[level]")
    @check_configured()
    async def am_bw(self, ctx, level: AutomodLevelConverter = None):
        """
        prevents people from saying certain words. use the `add`/`remove` subcommands to manage words, or use the `defaults` subcommand to enable the default word list
        """
        if not level:
            pun = self.states[ctx.guild.id].words
            words = self.states[ctx.guild.id].bad_words
            e = discord.Embed()
            e.description = f'Enabled - {"Yes" if pun != 0 else "No"}\nUsing default word list: {"Yes" if self.states[ctx.guild.id].default_filter else "No"}'
            if pun != 0:
                e.add_field(name="punishment level:", value=str(pun))

            if words:
                v = "\n".join(words)
            else:
                v = "No Words"

            v = v.strip()
            e.add_field(name="Banned Words:", value=v)
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].words = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Profanity punishment has been set to {'off' if level == 0 else level}")

    @am_bw.command("defaults", usage="<on/off>")
    @check_configured()
    async def am_bw_defaults(self, ctx, enabled: bool):
        state = self.states[ctx.guild.id]
        state.default_filter = enabled
        await self.bot.pg.execute("UPDATE automod SET default_wordlist = $1 WHERE guild_id = $2", enabled, ctx.guild.id)
        await ctx.send("Now using default word list" if enabled else "No longer using default word list")

    @am_bw.command("add", usage="<word>")
    @check_configured()
    async def am_bw_wa(self, ctx, word):
        """
        add a word to trigger the automod
        """
        await self.bot.pg.execute("INSERT INTO automod_triggers VALUES ($1, 1, $2);", ctx.guild.id, word)
        self.states[ctx.guild.id].bad_words.append(word)
        v = re.compile((
                           r'(?i)'  # case insensitive
                           r'\b'  # word bound
                           r'(?:{})'  # non capturing group, to make sure that the word bound occurs before/after all words
                           r'\b'
                       ).format('|'.join(map(re.escape, [a[0] for a in self.states[ctx.guild.id].bad_words]))))
        self.states[ctx.guild.id].regex = v
        await ctx.send(f"{ctx.author.mention} --> added {word} to blacklisted words")

    @am_bw.command("remove", usage="<word>")
    @check_configured()
    async def am_bw_wr(self, ctx, word):
        """
        remove a word trigger from the automod
        """
        if word in self.states[ctx.guild.id].bad_words:
            await self.bot.pg.execute(f"DELETE FROM automod_triggers WHERE guild_id = $1 AND word = $2 and type=1;", ctx.guild.id, word)
            self.states[ctx.guild.id].bad_words.remove(word)
            v = re.compile((
                               r'(?i)'  # case insensitive
                               r'\b'  # word bound
                               r'(?:{})'  # non capturing group, to make sure that the word bound occurs before/after all words
                               r'\b'
                           ).format('|'.join(map(re.escape, [a[0] for a in self.states[ctx.guild.id].bad_words]))))
            self.states[ctx.guild.id].regex = v
            await ctx.send(f"{ctx.author.mention} --> removed `{word}` from blacklisted words.")
        else:
            await ctx.send(f"{word} is not blacklisted")

    @automod.group("mentions", invoke_without_command=True, usage="[level]")
    @check_configured()
    async def am_mm(self, ctx, level: AutomodLevelConverter = None):
        """
        an automod that triggers when a user mentions multiple people in one message. defaults to 5+ people
        use `automod mentions amount X` to set the trigger threshold
        """
        state = self.states[ctx.guild.id]
        if level is None:
            e = discord.Embed(name="Help")
            fmt = f"Mass mentions protection is {'on' if state.mass_mentions != 0 else 'off'}"
            if state.mass_mentions != 0:
                fmt += f"\n{state.mass_mentions_amount} " \
                  f"mentions in one message are required to trigger automod"
                fmt += f"\nPunishment is set to level {state.mass_mentions}"

            e.description = fmt
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].mass_mentions = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Mass mentions punishment has been set to {'off' if level == 0 else level}")

    @am_mm.command("amount", usage="<amount>")
    @check_configured()
    async def am_mm_m(self, ctx, num: int):
        """
        set the amount of people that need to be mentioned for the automod to trigger
        """
        self.states[ctx.guild.id].mass_mentions_amount = num
        val = self.states[ctx.guild.id].value
        await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
        await ctx.send(f"Mass mentions threshold has been set to {num}")
    
    @automod.group("caps", invoke_without_command=True, usage="[level]")
    @check_configured()
    async def am_ac(self, ctx, level: AutomodLevelConverter=None):
        """
        edit the caps protection section of the automod.
        use `automod caps percent X` to set the caps percent
        """
        if level is None:
            punishment, perc = self.states[ctx.guild.id].caps, self.states[ctx.guild.id].caps_percent
            e = discord.Embed(name="Currently Enabled:", description=str(bool(punishment)))
            e.add_field(name="Caps Percentage", value=str(perc))
            e.add_field(name="Punishment", value=str(punishment))
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].caps = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Caps punishment has been set to {'off' if level == 0 else level}")

    @am_ac.command("percent", usage="<number: 1-100>")
    @check_configured()
    async def am_ac_ca(self, ctx, num: int):
        """
        set the percentage of caps that is needed to trigger the automod
        """
        await self.bot.pg.execute("UPDATE automod SET caps_percent = $1 WHERE guild_id = $2;", min(max(0,num),100), ctx.guild.id)
        self.states[ctx.guild.id].caps_percent = min(max(1,num),100)
        await ctx.send(f"{ctx.author.mention} --> set the caps percentage to {min(max(1,num),100)}%")
    
    @automod.group("links", invoke_without_command=True, usage="[level]")
    @check_configured()
    async def am_sl(self, ctx, level: AutomodLevelConverter = None):
        """
        begone advertisers! edit the links protection section of the automod.
        use `automod links add X` to add a blacklisted domain (note: do not include links to specific pages)
        """
        if level is None:
            punishment = self.states[ctx.guild.id].links
            e = discord.Embed()
            e.add_field(name="currently enabled: ", value="True" if punishment != 0 else "False")
            if punishment:
                e.add_field(name="punishment level", value=str(punishment))
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].links = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Links punishment has been set to {'off' if level == 0 else level}")

    @am_sl.command("add", usage="<domain>")
    @check_configured()
    async def am_sl_add(self, ctx, url):
        url = yarl.URL(url).host
        state = self.states[ctx.guild.id]

        if url in state.blacklisted_links:
            return await ctx.send("This domain is already blacklisted")

        await self.bot.pg.execute("INSERT INTO automod_triggers VALUES ($1,2,$2)", ctx.guild.id, url)
        state.blacklisted_links.append(url)
        await ctx.send(f"the domain <{url}> is now blacklisted")

    @am_sl.command("remove", usage="<domain>")
    async def am_sl_remove(self, ctx, url):
        url = url.replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        state = self.states[ctx.guild.id]

        if url not in state.blacklisted_links:
            return await ctx.send("This domain is not blacklisted")

        await self.bot.pg.execute("DELETE FROM automod_triggers WHERE guild_id = $1 AND word = $2 AND type = 2", ctx.guild.id, url)
        state.blacklisted_links.remove(url)
        await ctx.send(f"the domain <{url}> is no longer blacklisted")

    @automod.group("invites", invoke_without_command=True, usage="[level]")
    async def am_sdi(self, ctx, level: AutomodLevelConverter=None):
        """
        invite spammers? shut em up with this automod check!
        """
        if level is None:
            punishment = self.states[ctx.guild.id]['invites_punishment']
            e = discord.Embed()
            e.add_field(name="currently enabled: ", value="True" if punishment else "False")
            if punishment:
                e.add_field(name="punishment level", value=str(punishment))
            await ctx.send(embed=e)

        else:
            self.states[ctx.guild.id].invites = level
            val = self.states[ctx.guild.id].value
            await self.bot.pg.execute("UPDATE automod SET flags = $1 WHERE guild_id = $2", val, ctx.guild.id)
            await ctx.send(f"Invites punishment has been set to {'off' if level == 0 else level}")

    @automod.group("ignored", invoke_without_command=True)
    @check_configured()
    async def ignored(self, ctx):
        """
        use `automod ignored channels` or `automod ignored roles`
        """
        await ctx.send_help(ctx.command)

    @ignored.group("channels", invoke_without_command=True, usage="[add/remove]")
    @check_configured()
    async def am_ic(self, ctx):
        """
        configure ignored channels
        """
        state = self.states[ctx.guild.id]
        fmt = ", ".join([ctx.guild.get_channel(x).mention for x in state.ignored_channels if ctx.guild.get_channel(x) is not None])
        embed = commands.Embed()
        embed.description = f"Ignored Channels:\n{fmt}"
        await ctx.send(embed)

    @am_ic.command("add", usage="<channel>")
    @check_configured()
    async def am_ic_a(self, ctx, channel: discord.TextChannel):
        """
        add an ignored channel to the automod
        """
        state = self.states[ctx.guild.id]
        if channel.id in state.ignored_channels:
            return await ctx.send("channel is already ignored")

        state.ignored_channels.append(channel.id)
        await self.bot.pg.execute("INSERT INTO automod_ignore VALUES ($1,1,$2)", ctx.guild.id, channel.id)
        await ctx.send(f"{channel.mention} will no longer be regulated by automod")

    @am_ic.command("remove", usage="<channel>")
    @check_configured()
    async def am_ic_r(self, ctx, channel: discord.TextChannel):
        """
        remove an ignored channel from the automod
        """
        state = self.states[ctx.guild.id]

        if channel.id in state.ignored_channels:
            await self.bot.pg.execute("DELETE FROM automod_ignore WHERE guild_id = $1 AND id = $2 AND type = 1",
                                  ctx.guild.id, channel.id)
            state.ignored_channels.remove(channel.id)
            await ctx.send(f"{channel.mention} will now be monitored by automod")

        else:
            await ctx.send(f"{channel.mention} is already monitored by automod")

    @ignored.group("roles", invoke_without_command=True, usage="[add/remove]")
    @check_configured()
    async def am_ir(self, ctx):
        """
        shows the currently ignored roles
        """
        state = self.states[ctx.guild.id]
        fmt = ", ".join(
            [ctx.guild.get_role(x).mention for x in state.ignores_roles if ctx.guild.get_role(x) is not None])
        embed = commands.Embed()
        embed.description = f"Ignored Roles:\n{fmt}"
        await ctx.send(embed)

    @am_ir.command("add", usage="<role mention, id, or name>")
    @check_configured()
    async def am_ir_a(self, ctx, *, role: discord.Role):
        """
        add an ignored role to the automod
        """
        state = self.states[ctx.guild.id]
        if role.id in state.ignores_roles:
            return await ctx.send("channel is already ignored")

        state.ignores_roles.append(role.id)
        await self.bot.pg.execute("INSERT INTO automod_ignore VALUES ($1,2,$2)", ctx.guild.id, role.id)
        await ctx.send(f"{role.name} will no longer be regulated by automod")

    @am_ir.command("remove", usage="<channel>")
    @check_configured()
    async def am_ir_r(self, ctx, role: discord.Role):
        """
        remove an ignored role from the automod
        """
        state = self.states[ctx.guild.id]

        if role.id in state.ignores_roles:
            await self.bot.pg.execute("DELETE FROM automod_ignore WHERE guild_id = $1 AND id = $2 AND type = 2",
                                      ctx.guild.id, role.id)
            state.ignores_roles.remove(role.id)
            await ctx.send(f"{role.name} will now be monitored by automod")

        else:
            await ctx.send(f"{role.name} is already monitored by automod")
