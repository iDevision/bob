import datetime

import discord

from utils import db, commands
from utils.checks import *


def setup(bot):
    bot.add_cog(settings(bot))

index = {
    'moderation': "moderator",
    "quotes":"quotes",
    "giveaway":"giveaway",
    "automod":"automod",
    "modlogs":"modlogs",
    "community":"community",
    "fun":"fun",
    "music":"music",
    "autoresponder":"autoresponder",
    "events":"events",
    "currency":"currency",
    "modmail":"modmail",
    "basics":"basics",
    "commands":"commands",
    "tags":"tags",
    "qotd":"qotd",
    "twitch": "twitch_interg",
    "highlight": "highlight"
}
async def send_message(msg, user, messagable, embed=None, mention=True):
    if mention:
        msg = user.mention + " --> " + msg
    await messagable.send(msg, embed=embed)

class settings(commands.Cog):
    """
    The settings category. You need the `Bot Editor` role to edit anything in this category.
    """
    category = "settings"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("configs")
        self.stream_cache = {}
        async def chunk():
            v = await self.db.fetchall("SELECT guild_id, announce_streams, announce_channel_streams FROM guild_configs")
            for gid, AS, ACS in v:
                self.stream_cache[gid] = {"as": AS, "acs": ACS}
            for guild in self.bot.guilds:
                if guild.id not in self.stream_cache:
                    self.stream_cache[guild.id] = {"as": 0, "acs": 0}
        bot.loop.create_task(chunk())

    @commands.Cog.listener()
    async def on_guild_join(self, guild, *args):
        await self.db.execute("INSERT INTO guild_configs VALUES (?,0,0,0,0,3,?,5,0,0,'',0)", guild.id, "!" if self.bot.run_bot != "BOB_ALPHA" else "]")
        await self.bot.db.execute("INSERT INTO module_states VALUES (?,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)", guild.id)

    async def cog_check(self, ctx):
        return await basic_check(ctx, "editor")

    @commands.command(aliases=["modules"])
    async def module(self, ctx, module: str=None, state: bool=None):
        """
        toggle modules on or off to disable certain aspects of the bot
        use * for module to enable/disable all modules.
        use without arguments to see your server's current module states
        """
        if module is None:
            p = ""
            for a, b in self.bot.guild_module_states[ctx.guild.id].items():
                if b:
                    p += f"<:GreenTick:609893073216077825> - {a}\n"
                else:
                    p += f"<:RedTick:609893040328409108> - {a}\n"
            return await ctx.paginate_fields([("Modules", p)], per_page=4, embed_color=discord.Color.dark_magenta())
        else:
            if not await basic_check(ctx, "editor", "editor"):
                raise MissingRequiredRole("Missing The `Editor` Role to edit modules")
            if module == "*":
                if state is None:
                    raise commands.MissingRequiredArgument("state")
                for i in self.bot.guild_module_states[ctx.guild.id]:
                    self.bot.guild_module_states[ctx.guild.id][i] = state
                if not state:
                    await self.bot.db.execute("UPDATE module_states SET moderator=0, quotes=0, giveaway=0, automod=0, modlogs=0, community=0, fun=0, music=0, autoresponder=0, events=0, currency=0, modmail=0, basics=0, commands=0, tags=0, qotd=0, twitch_interg=0, highlight=0 WHERE guild_id IS ?", ctx.guild.id)
                else:
                    await self.bot.db.execute("UPDATE module_states SET moderator=1, quotes=1, giveaway=1, automod=1, modlogs=1, community=1, fun=1, music=1, autoresponder=1, events=1, currency=1, modmail=1, basics=1, commands=1, tags=1, qotd=1, twitch_interg=1, highlight=1 WHERE guild_id IS ?", ctx.guild.id)
                return await ctx.send(f"toggled all modules to {state}")
            if module.lower() not in self.bot.guild_module_states[ctx.guild.id]:
                return await ctx.send("Unknown Module: "+module)
            self.bot.guild_module_states[ctx.guild.id][module] = not self.bot.guild_module_states[ctx.guild.id][module]
            await self.bot.db.execute("UPDATE module_states SET %s=? WHERE guild_id IS ?"%index[module], int(self.bot.guild_module_states[ctx.guild.id][module]), ctx.guild.id)
            await ctx.send(f"toggled {module} to state {self.bot.guild_module_states[ctx.guild.id][module]}")

    @commands.group(invoke_without_command=True, usage="[config to assign] ...", aliases=['role'])
    async def roles(self, ctx, *args):
        """
        allows you to edit the role assignment. useful if you already have existing roles.
        `Mod`, for example.
        Current roles:
            `editor` - The `Bot Editor` role
            `muted` - The `Silenced` role
            `moderator` - Allows usage of Moderation Commands
            `manager` - Allows usage of Community Commands
        """
        roles = []
        for a,b in self.bot.guild_role_states[ctx.guild.id].items():
            r = ctx.guild.get_role(b)
            if r:
                r = f"{r.mention} - {r.name}"
            roles.append((a, r or "Not set or invalid role"))
        await ctx.paginate_fields(roles)

    @roles.command("editor", usage="<role>")
    async def r_editor(self, ctx, *, role: discord.Role):
        """
        set the `Bot Editor` role.
        requires the `Bot Editor` role or higher
        """
        await self.bot.db.execute("UPDATE roles SET editor = ? WHERE guild_id IS ?", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['editor'] = role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Bot Editor` role:"
        e.description = role.mention + " "
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)
    
    @roles.command("muted", usage="<role>")
    async def r_muted(self, ctx, *, role: discord.Role):
        """
        set the `Muted` role
        requires the `Bot Editor` role or higher
        """
        await self.bot.db.execute("UPDATE roles SET muted = ? WHERE guild_id IS ?", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['muted'] = role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Muted` role:"
        e.description = role.mention
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)
    
    @roles.command("moderator", usage="<role>")
    async def r_mod(self, ctx, *, role: discord.Role):
        """
        set the `Moderator` role
        requires the `Bot Editor` role or higher
        """
        await self.bot.db.execute("UPDATE roles SET moderator = ? WHERE guild_id IS ?", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['moderator'] = role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Moderator` role:"
        e.description = role.mention
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)
    
    @roles.command("manager", usage="<role>")
    async def r_com_manag(self, ctx, *, role: discord.Role):
        """
        set the `Community Manager` role
        requires the `Bot Editor` role or higher
        """
        await self.bot.db.execute("UPDATE roles SET manager = ? WHERE guild_id IS ?", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['manager'] = role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Community Manager` role:"
        e.description = role.mention
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)

    @roles.command("streamer", usage="<role>")
    async def r_com_stream(self, ctx, *, role: discord.Role):
        """
        set the `Community Manager` role
        requires the `Bot Editor` role or higher
        """
        await self.bot.db.execute("UPDATE roles SET streamer = ? WHERE guild_id IS ?", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['streamer'] =role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Streamer` role:"
        e.description = role.mention
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)

    @commands.group(invoke_without_command=True, usage="[subcommands]")
    async def configs(self, ctx, *args):
        """
        the settings for your server!
        """
        await ctx.send_help(ctx.command)

    @configs.command("announce.streams", usage="<true/false>")
    async def c_aas(self, ctx, enabled: bool):
        """
        announce community streams to a channel in your server!
        (WIP: create setting for only streamer role)
        """
        await self.db.execute("UPDATE guild_configs SET announce_streams=? WHERE guild_id IS ?", int(enabled), ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> updated `announcements.announce.streams` to {enabled}")

    @configs.command("announcements.channel", usage="<channel>")
    async def c_ac(self, ctx, chan: discord.TextChannel):
        """
        set the announcements channel. this is where events will go, if the events module is enabled and set up.
        """
        await self.db.execute("UPDATE guild_configs SET announce_channel=? WHERE guild_id IS ?", chan.id, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> updated `announcements.channel` to {chan}")

    @configs.command("channel.streams", usage="<channel>")
    async def c_acs(self, ctx, chan: discord.TextChannel):
        """
        set the community streams announcements channel.
        whenever someone ~~with the streamer role~~ (WIP) in your server goes live, it will be sent there.
        """
        await self.db.execute("UPDATE guild_configs SET announce_channel_streams=? WHERE guild_id IS ?",
                                  chan.id, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> updated `announcements.channel.streams` to {chan}")

    @configs.command("warns.before.silence", usage="<amount>")
    async def c_wbs(self, ctx, warnings: int):
        """
        set the amount of warnings before the person gets muted.
        the muted role must be in place for this to work
        """
        await self.db.execute("UPDATE guild_configs SET warns_before_silence=? WHERE guild_id IS ?", warnings, ctx.author.id)
        await ctx.send(f"{ctx.author.mention} --> updated `warns.before.silence` to `{warnings}`")

    @configs.command("prefix", usage="[prefix]")
    async def c_pref(self, ctx, prefix: str = None):
        """
        set the prefix for your server. you may only have one prefix. **Note:** you can always mention bob for help.
        """
        if not prefix:
            prefix = await self.db.fetch("SELECT prefix FROM guild_configs WHERE guild_id IS ?", ctx.guild.id)
            await send_message(f"The current server prefix is ``{prefix}``", ctx.author, ctx.channel)
        else:
            await self.db.execute("UPDATE guild_configs SET prefix = ? WHERE guild_id IS ?",
                                      prefix, ctx.guild.id)
            self.bot.guild_prefixes[ctx.guild.id] = prefix
            await send_message("set the server prefix to ``{0}``".format(prefix), ctx.author, ctx.channel)


    @configs.group("auto.assign.roles", invoke_without_command=True, usage="[subcommands]")
    async def c_aar(self, ctx):
        """
        set roles that will be automatically given to people when they join your server
        """
        e = discord.Embed(name="auto.assign.role")
        e.add_field(name="subcommands", value="add\nremove")
        roles = await (await self.db.execute("SELECT role_id FROM role_auto_assign WHERE guild_id IS ?", ctx.guild.id)).fetchall()
        if roles:
            v = ""
            for rid in roles:
                r = ctx.guild.get_role(rid)
                if r:
                    v += str(r)+"\n"
            e.add_field(name="current autoassign roles", value=v)
        else:
            e.add_field(name="current autoassign roles", value="*no autoassign roles*")
        await ctx.send(embed=e)


    @c_aar.command("add", usage="<role id or mention>")
    async def c_aar_a(self, ctx, role: discord.Role):
        """
        add a role to be autoassigned
        """
        try:
            await self.db.execute("INSERT OR FAIL INTO role_auto_assign VALUES (?,?)",
                                      ctx.guild.id, role.id)
        except:
            await ctx.send(f"{ctx.author.mention} --> failed to add {role.name} to autoassign. it may already be on autoassign")
            return
        await ctx.send(f"{ctx.author.mention} --> added ``{role.name}`` to autoassign")


    @c_aar.command("remove", usage="<role id or mention>")
    async def c_aar_r(self, ctx, role: discord.Role):
        """
        remove a role from being autoassigned
        """
        await self.db.execute("DELETE FROM role_auto_assign WHERE guild_id IS ? and ROLE_id IS ?", ctx.guild.id, role.id)
        await ctx.send(f"{ctx.author.mention} --> removed {role.name} from autoassign, if it was previously assigned.")
