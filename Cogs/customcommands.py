import asyncio
import random
import traceback
from typing import Optional

import discord
import viper
from viper.exts import discord as pyk_discord
from discord.ext.commands import converter
from discord.ext.commands.view import StringView
from jishaku.codeblocks import codeblock_converter

from utils import argparse
from utils import db, commands
from utils.checks import check_editor


def setup(bot):
    bot.add_cog(_CustomCommands(bot))


class _CustomCommands(commands.Cog):
    """
    this section allows you to make custom commands to use in your server.
    requires the `bot editor` role or higher.
    note that when making a custom command, **__DO NOT include a prefix__!** the server prefix will be used!
    """

    def __init__(self, bot):
        self.bot = bot

    async def parse(self, ctx, view: StringView, string: str) -> str:
        params = ""
        if view.eof:
            target = ctx.author
        else:
            possible_target = view.get_quoted_word()  # i do a quoted word here, in case it's not a mention
            ctx.bot = self.bot
            try:
                target = await converter.MemberConverter().convert(ctx, possible_target)
            except Exception:
                target = ctx.author
                params += possible_target
            params += view.read_rest()

        parameters = {
            "$authormention": ctx.author.mention,
            "$authorid": str(ctx.author.id),
            "$authorname": ctx.author.display_name,
            "$targetmention": target.mention,
            "$targetid": str(target.id),
            "$targetname": target.display_name
        }
        for trig, apply in parameters.items():
            string = string.replace(trig, apply)
        args = argparse.Adapter().parse(string, 1)
        ret = ""
        for i in args:
            if isinstance(i, str):
                ret += i
                continue
            if i['name'] == "random":
                ret += random.choice(i['params'])
        return ret

    async def parse_script(self, ctx, view, script):
        namespace = viper.VPNamespace()
        safe_context = pyk_discord.SafeAccessContext(ctx)
        namespace.buildmode(True)
        namespace['ctx'] = safe_context
        namespace['author'] = safe_context.author
        namespace['channel'] = safe_context.channel

        try:
            await viper.eval(script, defaults={"say": safe_context.send}, namespace=namespace, file=f"GuildScript {ctx.guild.id}", safe=True)
        except viper.VP_Error as e:
            await ctx.send(f"__Your script has encountered an error:__\n" + discord.utils.escape_markdown(e.format_stack()))

        except Exception as e:
            await ctx.send(f"__Your script has encountered an error:__\n" + discord.utils.escape_markdown(traceback.format_exception(type(e), e, e.__traceback__)))


    @commands.Cog.listener("on_message")
    async def trigger(self, message: discord.Message):
        if message.author.bot or not self.bot.setup or message.guild is None or not \
                self.bot.guild_module_states[message.guild.id]['commands']:
            return

        args = StringView(message.content)
        prefs = await self.bot.get_prefix(message)
        v = False
        if isinstance(prefs, list):
            for prefix in prefs:
                if message.content.startswith(prefix):
                    v = True
                    args.skip_string(prefix)
                    break

        else:
            if args.skip_string(prefs):
                v = True

        if not v:
            return

        com = args.get_word()
        args.skip_ws()

        data = await self.bot.pg.fetchrow("SELECT content, is_script FROM commands WHERE guild_id=$1 AND name=$2;", message.guild.id, com)
        if not data:
            return

        ctx = await self.bot.get_context(message)
        if not data['is_script']:
            v = await self.parse(ctx, args, data['content'])
            await message.channel.send(v)

        else:
            await self.parse_script(ctx, args, data['content'])

    async def guild_commands(self, guild):
        l = await self.bot.pg.fetch("SELECT name FROM commands WHERE guild_id=$1;", guild.id)
        ret = ""
        for i in l:
            ret += f"- {i['name']}\n"

        return ret or None

    @commands.group(invoke_without_command=True, aliases=['customcommands', "commands"])
    @commands.guild_only()
    @commands.check_module("commands")
    async def command(self, ctx: commands.Context):
        """
        you need the `Bot Editor` role to edit this category. call without arguments for a list of your server's commands.
        """
        formatted = await self.guild_commands(ctx.guild)
        if formatted is None:
            return await ctx.send("Your Server has no Custom Commands")

        await ctx.send(embed=commands.Embed(color=discord.Color.teal(), title="Your Server's custom commands",
                                            description=f"```md\n{formatted}\n```"))

    @command.command(aliases=['params'],
                     brief="this isnt actually a command, type `help commands parameters` to see the list of available parameters.")
    async def parameters(self, ctx):
        """
        __author parameters__
        $authormention  - mentions the author
        $authorname     - name of the author
        $authorid       - id of the author

        __target parameters__ (defaults to the author if no target is present)
        $targetmention  - mentions the target
        $targetname     - name of the target
        $targetid       - id of the target

        __other parameters__
        $random(arguments,seperated,by,commas) - picks a random value from the given arguments. escape commas by doing `\\,`
        """

    @command.command(aliases=['show'])
    @commands.check_module("commands")
    async def raw(self, ctx, cmd):
        """
        show the command without any argument parsing
        """
        v = await self.bot.pg.fetchval("SELECT content FROM commands WHERE guild_id=$1 AND name=$2", ctx.guild.id, cmd)
        if v is None:
            return await ctx.send("That command does not exist")

        await ctx.send(v)

    @command.command(aliases=["add"], usage="<command name> [is_script=No] <command response>")
    @check_editor()
    @commands.check_module("commands")
    async def create(self, ctx, name: str, is_script: Optional[bool], *, response: codeblock_converter):
        """
        create a new custom command.
        requires the `bot editor` role or higher.
        note that there is no sanitization on this. pings will remain, and will ping every time the command is used.
        """
        if is_script is None:
            is_script = False

        response = response.content

        if name in self.bot.all_commands:
            return await ctx.send("that command is reserved by built in commands!")

        await self.bot.pg.execute("INSERT INTO commands VALUES ($1,$2,$3,$4,$5,$6)",
                                  ctx.guild.id, name, response, 0, 0, is_script)
        return await ctx.send(f"{ctx.author.mention}, added command {name}")

    @command.command(usage="<command name> <command response>")
    @check_editor()
    @commands.check_module("commands")
    async def edit(self, ctx, name: str, *, response: codeblock_converter):
        """
        edits an already existing custom command.
        requires the `bot editor` role or higher.
        """
        response = response.content

        if await self.bot.pg.execute("UPDATE commands SET content = $1 WHERE guild_id = $2 AND name=$3 RETURNING *;",
                                     response, ctx.guild.id, name):
            await ctx.send(f"updated command `{name}`")

        else:
            await ctx.send(f"No command named `{name}`")

    @command.command(aliases=['delete', 'rm'], usage="<command name>")
    @check_editor()
    async def remove(self, ctx, name: str):
        """
        deletes a custom command.
        requires the `bot editor` role or higher.
        """
        query = "DELETE FROM commands WHERE guild_id=$1 AND name=$2 RETURNING *;"
        p = await self.bot.pg.fetch(query, ctx.guild.id, name)
        if p:
            await ctx.send(f"Removed command {name}")

        else:
            await ctx.send(f"No command named {name}")
