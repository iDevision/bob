import discord

from utils import db, commands
from utils.checks import *


def setup(bot):
    bot.add_cog(automodCog(bot))

class automodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("automod")
        self.states = self.bot.automod_states
        if not self.states:
            self.bot.loop.create_task(self.on_ready())

    async def cog_check(self, ctx):
        return await basic_check(ctx, "editor") and check_module("automod")

    @commands.Cog.listener()
    async def on_guild_join(self, guild, *args):
        self.states[guild.id] = {"banned_words_punishment": 0, "message_spam_messages": 5, "message_spam_delay": 2, "message_spam_punishment": 0, "mass_mentions_max": 4, "mass_mentions_punishment": 0,
                                 "all_caps_punishment": 0, "all_caps_percent": 100, "invites_punishment": 0, "links_punishment": 0, "banned_words": [], "channel": 0}
        await self.db.execute("INSERT INTO automod_config VALUES (?,0,0,5,2,0,4,0,0,100,0,0)", guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        v = await self.db.fetchall("SELECT * FROM automod_config")
        for i in v:
            gid, channel, banned_words_punishment, message_spam_messages, message_spam_delay, message_spam_punishment, mass_mentions_max, mass_mentions_punishment, all_caps_punishment, all_caps_percent, invites_punishment, links_punishment = i
            self.bot.automod_states[gid] = {"banned_words_punishment": banned_words_punishment, "message_spam_messages": message_spam_messages, "message_spam_delay": message_spam_delay,
             "message_spam_punishment": message_spam_punishment, "mass_mentions_max": mass_mentions_max, "mass_mentions_punishment": mass_mentions_punishment,
             "all_caps_punishment": all_caps_punishment, "all_caps_percent": all_caps_percent, "invites_punishment": invites_punishment, "links_punishment": links_punishment,
             "banned_words": [], "channel": channel}
            c = await self.db.fetchall("SELECT word FROM automod_banned_words WHERE guild_id IS ?", gid)
            if c:
                self.bot.automod_states[gid]['banned_words'] = [a[0] for a in c]

    @commands.group(invoke_without_command=True, usage="[subcommands]")
    async def automod(self, ctx):
        """
        allows the editing of the automod.
        requires the `bot editor` role to edit anything in this category
        all subcommands have a `punishment` subcommand, some may have others as well
        """
        await ctx.send_help(ctx.command)

    @automod.group(invoke_without_command=True, usage="<channel>")
    async def channel(self, ctx, channel: discord.TextChannel=None):
        """
        set the channel to output automod logs to. type `reset` to remove the automod log channel.
        """
        if channel:
            await self.db.execute("UPDATE automod_config SET enabled = ? WHERE guild_id IS ?", channel.id, ctx.guild.id)
            self.states[ctx.guild.id]['channel'] = channel.id
            await ctx.send(f"{ctx.author.mention} --> set automod channel to {channel.mention}")
        else:
            c = self.states[ctx.guild.id]['channel']
            if c:
                c = self.bot.get_channel(c)
                if not c:
                    return await ctx.send(f"{ctx.author.mention} --> invalid automod channel!")
                await ctx.send(f"{ctx.author.mention} --> automod output channel: {c.mention}")
            else:
                await ctx.send(f"{ctx.author.mention} --> no automod output channel")

    @channel.command(usage="(no parameters)")
    async def reset(self, ctx):
        """
        removes the automod logging channel
        """
        await self.db.execute("UPDATE automod_config SET enabled = 0 WHERE guild_id IS ?", ctx.guild.id)
        self.states[ctx.guild.id]['channel'] = 0
        await ctx.send(f"{ctx.author.mention} --> reset automod channel")

    @automod.group("message.spam", invoke_without_command=True, usage="[subcommands]")
    async def am_ms(self, ctx):
        """
        message spam automod protects against users spamming a channel
        """
        pun = self.states[ctx.guild.id]
        e = discord.Embed(name="Currently Enabled: ")
        e.description = "True" if pun != 0 else "False"
        e.add_field(name="punishment", value=str(pun))
        await ctx.send(embed=e)

    @am_ms.command("punishment", usage="<number: 0-5>")
    async def am_ms_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            await ctx.send_help(ctx.command)
            return
        await self.db.execute("UPDATE automod_config SET message_spam_punishment = ? WHERE guild_id IS ?", num, ctx.guild.id)
        self.states[ctx.guild.id]['message_spam_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod check")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")

    @automod.group("banned.words", invoke_without_command=True, usage="[subcommands]")
    async def am_bw(self, ctx):
        """
        prevents people from saying certain words. use the `add`/`remove` subcommands to manage words
        """
        pun = self.states[ctx.guild.id]['banned_words_punishment']
        words = self.states[ctx.guild.id]['banned_words']
        e = discord.Embed(title="Currently Enabled: ")
        e.description = "True" if pun != 0 else "False"
        e.add_field(name="punishment level:", value=str(pun))
        v = ""
        if words:
            for record in words:
                v += record[0] + "\n"
        else:
            v = "No Words"
        v = v.strip()
        e.add_field(name="Banned Words:", value=v)
        await ctx.send(embed=e)

    @am_bw.command("add", usage="<word>")
    async def am_bw_wa(self, ctx, word):
        """
        add a word to trigger the automod
        """
        await self.db.execute("INSERT OR IGNORE INTO automod_banned_words VALUES (?, ?)", ctx.guild.id, word)
        self.states[ctx.guild.id]['banned_words'].append(word)
        await ctx.send(f"{ctx.author.mention} --> added {word} to banned.words")

    @am_bw.command("remove", usage="<word>")
    async def am_bw_wr(self, ctx, words):
        """
        remove a word trigger from the automod
        """
        await self.db.execute(f"DELETE FROM automod_banned_words WHERE guild_id IS {ctx.guild.id} AND word IS ?", words)
        self.states[ctx.guild.id]['banned_words'].remove(words)
        await ctx.send(f"{ctx.author.mention} --> removed `{words}` from banned words, if it was previously banned")

    @am_bw.command("punishment", usage="<number: 0-5>")
    async def am_bw_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            await ctx.send_help(ctx.command)
            return
        await self.db.execute("UPDATE automod_config SET banned_words_punishment = ? WHERE guild_id IS ?",
                                  (num, ctx.guild.id))
        self.states[ctx.guild.id]['banned_words_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod check")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")

    @automod.group("mass.mentions", invoke_without_command=True, usage="[subcommands]")
    async def am_mm(self, ctx):
        """
        an automod that triggers when a user mentions multiple people in one message. defaults to 5+ people
        """
        punishment, maxs = self.states[ctx.guild.id]['mass_mentions_punishment'], self.states[ctx.guild.id]['mass_mentions_max']
        e = discord.Embed(name="Help")
        e.add_field(name="currently enabled: ", value="True" if punishment != 0 else "False")
        e.add_field(name="Max mentions", value=str(maxs))
        e.add_field(name="Punishment", value=punishment)
        await ctx.send(embed=e)

    @am_mm.command("punishment", usage="<number: 0-5>")
    async def am_mm_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            await ctx.send_help(ctx.command)
            return
        await self.db.execute("UPDATE automod_config SET mass_mentions_punishment = ? WHERE guild_id IS ?",
                                  (num, ctx.guild.id))
        self.states[ctx.guild.id]['mass_mentions_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod submodule")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")
    
    
    @am_mm.command("trigger", usage="<number>")
    async def am_mm_m(self, ctx, num: int):
        """
        set the amount of people that need to be mentioned for the automod to trigger
        """
        await self.db.execute("UPDATE automod_config SET mass_mentions_max = ? WHERE guild_id IS ?", num, ctx.guild.id)
        self.states[ctx.guild.id]['mass_mentions_max'] = num
        await ctx.send(f"{ctx.author.mention} --> set the max allowed mentions to {str(num)}")
    
    
    @automod.group("caps.protection", invoke_without_command=True, usage="[subcommands]")
    async def am_ac(self, ctx):
        """
        edit the caps protection section of the automod
        """
        punishment, perc = self.states[ctx.guild.id]['all_caps_punishment'], self.states[ctx.guild.id]['all_caps_percent']
        e = discord.Embed(name="Currently Enabled:", description=str(bool(punishment)))
        e.add_field(name="Caps Percentage", value=str(perc))
        e.add_field(name="Punishment", value=str(punishment))
        await ctx.send(embed=e)

    @am_ac.command("percent", usage="<number (percentage)>")
    async def am_ac_ca(self, ctx, num: int):
        """
        set the percentage of caps that is needed to trigger the automod
        """
        await self.db.execute("UPDATE automod_config SET all_caps_percent = ? WHERE guild_id IS ?", min(max(0,num),100), ctx.guild.id)
        self.states[ctx.guild.id]['all_caps_percent'] = min(max(0,num),100)
        await ctx.send(f"{ctx.author.mention} --> set the caps percentage to {min(max(0,num),100)}")

    @am_ac.command("punishment", usage="<number: 0-5>")
    async def am_ac_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            return await ctx.send_help(ctx.command)
        await self.db.execute("UPDATE automod_config SET all_caps_punishment = ? WHERE guild_id IS ?",
                               num, ctx.guild.id)
        self.states[ctx.guild.id]['all_caps_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod submodule")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")
    
    
    @automod.group("stop.links", invoke_without_command=True, usage="[subcommands]")
    async def am_sl(self, ctx):
        """
        begone advertisers!
        """
        punishment = self.states[ctx.guild.id]['links_punishment']
        e = discord.Embed()
        e.add_field(name="currently enabled: ", value="True" if punishment else "False")
        if punishment:
            e.add_field(name="punishment level", value=str(punishment))
        await ctx.send(embed=e)

    @am_sl.command("punishment", usage="<number: 0-5>")
    async def am_sl_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            await ctx.send_help(ctx.command)
            return
        await self.db.execute("UPDATE automod_config SET links_punishment = ? WHERE guild_id IS ?",
                                  (num, ctx.guild.id))
        self.states[ctx.guild.id]['links_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod submodule")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")

    @automod.group("discord.invites", invoke_without_command=True, usage="[subcommands]")
    async def am_sdi(self, ctx):
        """
        invite spammers? shut em up with this automod check!
        """
        punishment = self.states[ctx.guild.id]['invites_punishment']
        e = discord.Embed()
        e.add_field(name="currently enabled: ", value="True" if punishment else "False")
        if punishment:
            e.add_field(name="punishment level", value=str(punishment))
        await ctx.send(embed=e)

    @am_sdi.command("punishment", usage="<number: 0-5>")
    async def am_sdi_p(self, ctx, num: int):
        """
        set the punishment. severity is as follows:
        `0` - disabled
        `1` - delete the message
        `2` - delete the message and warn the user
        `3` - delete the message and silence the user
        `4` - delete the message and kick the user
        """
        if num > 4 or num < 0:
            await ctx.send(f"{ctx.author.mention} --> Invalid punishment!")
            await ctx.send_help(ctx.command)
            return
        await self.db.execute("UPDATE automod_config SET invites_punishment = ? WHERE guild_id IS ?",
                                  num, ctx.guild.id)
        self.states[ctx.guild.id]['invites_punishment'] = num
        if not num:
            await ctx.send(f"{ctx.author.mention} --> disabled automod submodule")
        else:
            await ctx.send(f"{ctx.author.mention} --> set the punishment to {num}")

    @automod.group("ignored.channels", invoke_without_command=True, usage="[subcommands]", hidden=True)
    async def am_ic(self, ctx):
        """
        shows the ignored channels
        (note that ignored channels dont actually *do* anything as of now :( )
        """
        pass

    @am_ic.command("add", usage="<channel>")
    async def am_ic_a(self, ctx, channel: discord.TextChannel):
        """
        add an ignored channel to the automod
        (note this doesnt actually *do* anything yet :( )
        """
        try:
            await self.db.execute("INSERT OR FAIL INTO automod_ignore VALUES (?,?,?)", ctx.guild.id, "channel", channel.id)
        except:
            await ctx.send(f"{ctx.author.mention} --> failed to ignore {channel.mention}")
        await ctx.send(f"{ctx.author.mention} --> channel {channel.mention} will no longer be regulated by automod.")

    @am_ic.command("remove", usage="<channel>")
    async def am_ic_r(self, ctx, channel: discord.TextChannel):
        """
        remove an ignored channel from the automod
        (note that this doesnt actually do anything yet :( )
        """
        await self.db.execute("DELETE FROM automod_ignore WHERE guild_id IS ? AND ignore_id IS ? AND type IS ?",
                                  ctx.guild.id, channel.id, "channel")
        await ctx.send(f"{ctx.author.mention} --> {channel.mention} will now be monitored by automod, if it "
                       f"was previously ignored.")

    @automod.group("ignored.roles", invoke_without_command=True, usage="[subcommmands]", hidden=True)
    async def am_ir(self, ctx):
        """
        shows the currently ignored roles
        (note that ignored roles dont actually *do* anything :(  )
        """

    @am_ir.command("add", usage="<channel>")
    async def am_ir_a(self, ctx, role: discord.Role):
        """
        add an ignored role to the automod
        """
        try:
            await self.db.execute("INSERT OR FAIL INTO automod_ignore VALUES (?,?,?)",
                                      ctx.guild.id, "role", role.id)
        except:
            await ctx.send(f"{ctx.author.mention} --> failed to ignore {role.name}")
            return
        await ctx.send(f"{ctx.author.mention} --> people with the `{role.name}` role will no longer be monitored by automod")

    @am_ir.command("remove", usage="<channel>")
    async def am_ir_r(self, ctx, role: discord.Role):
        """
        remove an ignored role from the automod
        """
        await self.db.execute("DELETE FROM automod_ignore WHERE guild_id IS ? AND type IS ? AND ignore_id IS ?",
                                  ctx.guild.id, "role", role.id)
        await ctx.send(f"{ctx.author.mention} --> the {role.name} role will now be monitored, if it was not monitored before. "
                       f"(note that people with other ignored role will not be monitored.)")
