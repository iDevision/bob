import datetime

import discord

from utils import db, commands, objects
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

class settings(commands.Cog):
    """
    The settings category. You need the `Bot Editor` role to edit anything in this category.
    """
    category = "settings"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("configs")

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

                self.bot.guild_module_states[ctx.guild.id] = {x: state for x in self.bot.guild_module_states[ctx.guild.id]}
                await self.bot.pg.execute("UPDATE modules SET flags = $1 WHERE guild_id = $2", objects.save_modules({}, state), ctx.guild.id)
                return await ctx.send(f"toggled all modules to {state}")

            if module.lower() not in self.bot.guild_module_states[ctx.guild.id]:
                return await ctx.send("Unknown Module: "+module)

            self.bot.guild_module_states[ctx.guild.id][module] = state
            states = objects.save_modules(self.bot.guild_module_states[ctx.guild.id])
            await self.bot.pg.execute("UPDATE modules SET flags = $1 WHERE guild_id = $2", states, ctx.guild.id)
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
            if a == "streamer":
                continue

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
        await self.bot.pg.execute("UPDATE roles SET editor = $1 WHERE guild_id = $2", role.id, ctx.guild.id)
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
        await self.bot.pg.execute("UPDATE roles SET muted = $1 WHERE guild_id = $2", role.id, ctx.guild.id)
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
        await self.bot.pg.execute("UPDATE roles SET moderator = $1 WHERE guild_id = $2", role.id, ctx.guild.id)
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
        await self.bot.pg.execute("UPDATE roles SET manager = $1 WHERE guild_id = $2", role.id, ctx.guild.id)
        self.bot.guild_role_states[ctx.guild.id]['manager'] = role.id
        e = discord.Embed(color=discord.Color.teal())
        e.title = "Assigned `Community Manager` role:"
        e.description = role.mention
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)

    @commands.group("prefix", invoke_without_command=True)
    async def c_pref(self, ctx):
        """
        view your server's prefixes. use `prefix add` and `prefix remove` to add/remove prefixes
        """
        prefixes = await self.bot.pg.fetch("SELECT prefix FROM prefixes WHERE guild_id = $1", ctx.guild.id)
        emb = ctx.embed_invis(title=f"{ctx.guild.name}'s prefixes")
        emb.description = "\n".join(x['prefix'] for x in prefixes) + "\n" + ctx.guild.me.mention
        await ctx.send(embed=emb)

    @c_pref.command("add")
    @commands.check_editor()
    async def _add(self, ctx, prefix: commands.clean_content):
        """
        adds a prefix to your server!
        """
        await self.bot.pg.execute("INSERT INTO prefixes VALUES ($1,$2)", ctx.guild.id, prefix)
        self.bot.guild_prefixes[ctx.guild.id].append(prefix)
        await ctx.send(f"{prefix} is now a prefix")

    @c_pref.command("remove")
    @commands.check_editor()
    async def _remove(self, ctx, *, prefix: commands.clean_content):
        """
        removes a prefix from your server!
        """

        try:
            self.bot.guild_prefixes[ctx.guild.id].remove(prefix)
        except:
            await ctx.send(f"could not remove `{prefix}`, as it did not exist (you cannot remove the mention prefix)")
            return
        pref = await self.bot.pg.fetchrow("DELETE FROM prefixes WHERE guild_id = $1 AND prefix = $2 RETURNING *;",
                                          ctx.guild.id, prefix)
        if pref:
            await ctx.send(f"{prefix} will no longer be used as a prefix")
        else:
            await ctx.send(f"could not remove `{prefix}`, as it did not exist (you cannot remove the mention prefix)")


    @commands.group("autorole", invoke_without_command=True, usage="[subcommands]")
    async def c_aar(self, ctx):
        """
        set roles that will be automatically given to people when they join your server
        """
        e = discord.Embed(name="auto.assign.role")
        e.add_field(name="subcommands", value="add\nremove")
        roles = await self.bot.pg.fetch("SELECT role_id FROM role_assign WHERE guild_id = $1", ctx.guild.id)
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
    @commands.check_editor()
    async def c_aar_a(self, ctx, role: discord.Role):
        """
        add a role to be autoassigned
        """
        try:
            await self.bot.pg.execute("INSERT INTO role_assign VALUES ($1,$2)",
                                      ctx.guild.id, role.id)
        except:
            return await ctx.send(f"{ctx.author.mention} --> failed to add {role.name} to autoassign. it may already be on autoassign")

        await ctx.send(f"{ctx.author.mention} --> added ``{role.name}`` to autoassign")


    @c_aar.command("remove", usage="<role id or mention>")
    @commands.check_editor()
    async def c_aar_r(self, ctx, role: discord.Role):
        """
        remove a role from being autoassigned
        """
        v = await self.db.fetch("DELETE FROM role_auto_assign WHERE guild_id = $1 and role_id = $2 RETURNING *;", ctx.guild.id, role.id)
        if v:
            await ctx.send(f"Removed {role.name} from auto assign")

        else:
            await ctx.send(f"{role.name} could not be removed from auto assign, as it is not set to be auto assigned")
