import asyncio
import random

import discord
from discord.ext.commands import converter

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
        self.db = db.Database("customcommands")

    async def parse(self, ctx, view, string: str):
        params = ""
        if view.eof:
            target = ctx.author
        else:
            possible_target = view.get_quoted_word() # i do a quoted word here, in case it's not a mention
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

    @commands.Cog.listener("on_message")
    async def trigger(self, message: discord.Message):
        if message.author.bot or not self.bot.setup or message.guild is None or not self.bot.guild_module_states[message.guild.id]['commands']:
            return
        from discord.ext.commands.view import StringView
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
            if message.content.startswith(prefs):
                args.skip_string(prefs)
                v = True
        if not v:
            return

        com = args.get_word()
        args.skip_ws()
        v = await self.db.fetch("SELECT response FROM custom_commands WHERE guild_id IS ? AND trigger IS ?", message.guild.id, com)
        if not v:
            return
        ctx = await self.bot.get_context(message)
        v = await self.parse(ctx, args, v)
        await message.channel.send(v)

    @commands.group(invoke_without_command=True, aliases=['customcommands', "commands"])
    @commands.guild_only()
    async def command(self, ctx: commands.Context):
        """
        you need the `Bot Editor` role to edit this category. call without arguments for a list of your server's commands.
        """
        l = await self.db.fetchall("SELECT trigger FROM custom_commands WHERE guild_id IS ?", ctx.guild.id)
        if not l:
            return await ctx.send("Your Server has no Custom Commands")
        formatted = "```md\n"
        for i in l:
            formatted += f"- {i[0]}\n"
        formatted += "```"
        await ctx.send(embed=commands.Embed(color=discord.Color.teal(), title="Your Server's custom commands", description=formatted))

    @command.command(aliases=['params'], brief="this isnt actually a command, type `help commands parameters` to see the list of available parameters.")
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
    async def raw(self, ctx, command):
        """
        show the command without any argument parsing
        """
        v = await self.db.fetch("SELECT response FROM custom_commands WHERE guild_id IS ? AND trigger IS ?", ctx.guild.id, command)
        if not v:
            return await ctx.send(f"No custom command called {command} found!")
        await ctx.send(await commands.clean_content().convert(ctx, v))

    @command.command(aliases=["add"], usage="<command name> <command response>")
    @check_editor()
    async def create(self, ctx, name: str, *, response: commands.clean_content = None):
        """
        create a new custom command.
        requires the `bot editor` role or higher
        """
        if name in self.bot.all_commands:
            return await ctx.send("that command is reserved!")
        cur = await self.db.execute("SELECT * FROM custom_commands WHERE guild_id IS ? AND trigger IS ?", ctx.guild.id, name)
        if await cur.fetchone():
            await ctx.send(f"{ctx.author.mention} --> that command already exists!")
        else:
            if response is None:
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel

                await ctx.send(
                    f"{ctx.author.mention} --> ok, so the command is named `{name}`. what should the content be?")
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=120)
                except asyncio.TimeoutError:
                    return await ctx.send("time limit reached. aborting.")
                if msg.content == ctx.prefix + "cancel":
                    return await ctx.send(f"{ctx.author.mention} --> aborting")
                response = await commands.clean_content().convert(ctx, msg.content)
            await self.db.execute("INSERT INTO custom_commands VALUES "
                                         "(?, ?, ?, ?);", ctx.guild.id, name, response, 0)
            await ctx.send(f"{ctx.author.mention} --> added command {name}")


    @command.command(usage="<command name> <command response>")
    @check_editor()
    async def edit(self, ctx, name: str, *, response: str = None):
        """
        edits an already existing custom command.
        requires the `bot editor` role or higher.
        """
        v = await self.db.fetchrow("SELECT * FROM custom_commands WHERE guild_id IS ? AND trigger IS ?", ctx.guild.id, name)
        if not v:
            await ctx.send(f"{ctx.author.mention} --> that command doesn't exist!")
            return
        else:
            if response is None:
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel

                await ctx.send(
                    f"{ctx.author.mention} --> ok, so the command is named `{name}`. what should the content be?")
                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=120)
                except asyncio.TimeoutError:
                    return await ctx.send("time limit reached. aborting.")
                if msg.content == ctx.prefix + "cancel":
                    return await ctx.send(f"{ctx.author.mention} --> aborting")
                response = await commands.clean_content().convert(ctx, msg.content)
            await self.db.execute("UPDATE custom_commands SET response = ? WHERE guild_id IS ? AND trigger IS ?", response, ctx.guild.id, name)
            await ctx.send(f"{ctx.author.mention} --> updated command `{name}`")


    @command.command(aliases=['delete', 'rm'], usage="<command name>")
    @check_editor()
    async def remove(self, ctx, name: str):
        """
        deletes a custom command.
        requires the `bot editor` role or higher.
        """
        v = await self.db.fetchrow("SELECT * FROM custom_commands WHERE guild_id is ? and trigger IS ?", ctx.guild.id, name)
        if not v:
            await ctx.send(f"{ctx.author.mention} --> that command does not exist!")
        else:
            await self.db.execute("DELETE FROM custom_commands WHERE guild_id is ? AND trigger IS ?", ctx.guild.id, name)
            await ctx.send(f"{ctx.author.mention} --> removed command {name}")
