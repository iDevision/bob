import asyncio

import discord
from discord import utils

from utils import commands, errors, objects
from utils.checks import *

def setup(bot):
    bot.add_cog(_modlogs(bot))

def ensure_logging(state=True):
    def predicate(ctx):
        msg = f"Logging is not initialized for this server. Use `{utils.escape_mentions(ctx.prefix)}logs init` to do so."
        if state:
            v = ctx.guild.id in ctx.bot.logging_states and ctx.bot.logging_states[ctx.guild.id] is not None
            if not v:
                raise commands.CheckFailure(msg)

            else:
                return True

        else:
            if ctx.guild.id not in ctx.bot.logging_states:
                return True

            if ctx.bot.logging_states[ctx.guild.id] is not None:
                raise commands.CheckFailure(f"logging is already initialized")

            return True
    return commands.check(predicate)

class _modlogs(commands.Cog):
    """
    allows you to edit the `modlogs` module of the bot
    requires the `bot editor` role
    """
    def __init__(self, bot):
        self.bot = bot
        self.cache = bot.logging_states

    async def cog_check(self, ctx):
        if not self.bot.guild_module_states[ctx.guild.id]['modlogs']:
            raise errors.ModuleDisabled("modlogs")

        return True

    @commands.Cog.listener()
    async def on_message(self, message: commands.Message):
        if message.author.bot or not message.content or not message.guild:
            return

        if message.guild.id not in self.cache:
            await asyncio.sleep(5) # the on_message event is being called after this one. wait for it to complete (which hopefully wont take more than 5 seconds)

        if message.guild.id not in self.cache:
            return # forget it

        state = self.cache[message.guild.id] #type: objects.LoggingFlags

        if state is None:
            return

        if not state.message_delete and not state.message_edit:
            return

        await self.bot.pg.execute("INSERT INTO modlog_messages VALUES ($1,$2,$3,$4,$5,$6)", message.guild.id,
                                  message.channel.id, message.id, message.author.id, message.created_at, message.content)

    @commands.group(invoke_without_command=True, aliases=['logs', 'logger'], walk_help=False)
    @ensure_logging()
    async def modlogs(self, ctx):
        """
        set up logging for your server.
        you need the `Bot Editor` role to use this category
        """
        state = self.cache[ctx.guild.id]
        def getstate(s):
            if s:
                return ON
            return OFF

        ON = "<:slide_yes:697928162834645053>"
        OFF = "<:slide_no:697928214479110254>"

        fmt =  f"user join      - {getstate(state.member_join)}\n"
        fmt += f"user edit      - {getstate(state.member_update)}\n"
        fmt += f"user leave     - {getstate(state.member_leave)}\n"
        fmt += f"channel create - {getstate(state.channel_create)}\n"
        fmt += f"channel edit   - {getstate(state.channel_edit)}\n"
        fmt += f"channel delete - {getstate(state.channel_delete)}\n"
        fmt += f"role create    - {getstate(state.role_create)}\n"
        fmt += f"role edit      - {getstate(state.role_edit)}\n"
        fmt += f"role delete    - {getstate(state.role_delete)}\n"
        fmt += f"message edit   - {getstate(state.message_edit)}\n"
        fmt += f"message delete - {getstate(state.message_delete)}\n"
        fmt += f"emojis         -  {getstate(state.emojis_update)}"

        embed = ctx.embed_invis()
        embed.title = "Logging Overview"
        embed.description = f"channel - {ctx.guild.get_channel(state.channel).mention if ctx.guild.get_channel(state.channel) else 'None set'}\n{fmt}"
        await ctx.send(embed=embed)

    @modlogs.command()
    @ensure_logging(False)
    async def init(self, ctx):
        """
        initializes logging for your guild.
        """
        record = await self.bot.pg.fetchrow("INSERT INTO modlogs VALUES ($1,$2,$3) RETURNING *;", ctx.guild.id, 0, 0)
        self.cache[ctx.guild.id] = objects.LoggingFlags(self.bot.pg, record)
        await ctx.send("Logging is now initialized for this server")

    @modlogs.group("goto", invoke_without_command=True, usage="<channel or 'remove'>", aliases=["logchannel"])
    @ensure_logging()
    @check_editor()
    async def ms_chan(self, ctx, channel: discord.TextChannel=None):
        """
        set the channel your logs should go to.
        note that some logs may duplicate with the automod logs.
        """
        state = self.cache[ctx.guild.id] #type: objects.LoggingFlags

        if not channel:
            channel = state.channel
            channel = self.bot.get_channel(channel)

            if not channel:
                return await ctx.send("Invalid or no logs channel!")

            return await ctx.send(f"Logs are being sent to {channel.mention}")

        state.channel = channel.id
        await state.save()

        await ctx.send(f"set the logging channel to {channel.mention}")

    @modlogs.command("all")
    @ensure_logging()
    @check_editor()
    async def mm_all(self, ctx, on: bool):
        """
        a quick way to set everything on or off
        """
        state = self.cache[ctx.guild.id]
        if on:
            state.value = 16325
        else:
            state.value = 0
        await state.save()
        await ctx.send(f"set all logs to {'on' if on else 'off'}")

    @ms_chan.command(aliases=['clear'])
    @ensure_logging()
    @check_editor()
    async def remove(self, ctx):
        """
        remove the logs channel. effectively stops logging.
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        state.channel = None
        await state.save()

        await ctx.send(f"removed logging channel")

    @modlogs.group(aliases=['users', 'member', 'members'])
    async def user(self, ctx):
        """
        logs user <join/edit/leave> [on/off]
        """
        pass

    @user.command("join")
    @ensure_logging()
    @check_editor()
    async def mmbrjoin(self, ctx, enabled: bool=None):
        """
        enable/disable logging for users joining your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.member_join = enabled
            await state.save()

            return await ctx.send(f"users joining will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"users joining is{' not' if not state.member_join else ''} being logged")

    @user.command("leave")
    @ensure_logging()
    @check_editor()
    async def mmbreleave(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users leaving your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.member_leave = enabled
            await state.save()

            return await ctx.send(f"users leaving will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"users leaving is{' not' if not state.member_leave else ''} being logged")

    @user.command("edit", aliases=['update'])
    @ensure_logging()
    @check_editor()
    async def mmbredit(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users being edited your server.
        editing can be things such as nickname updates, roles being added/removed, and the like.
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.member_join = enabled
            await state.save()

            return await ctx.send(f"user edits will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"user edits is{' not' if not state.member_update else ''} being logged")

    @user.command("ban")
    @ensure_logging()
    @check_editor()
    async def mmbrban(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users being banned from your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.member_ban = enabled
            await state.save()

            return await ctx.send(f"users being banned will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"users being banned is{' not' if not state.member_ban else ''} being logged")

    @user.command("unban")
    @ensure_logging()
    @check_editor()
    async def mmbrunban(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users being unbanned from your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.member_unban = enabled
            await state.save()

            return await ctx.send(f"users being unbanned will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"users being unbanned is{' not' if not state.member_unban else ''} being logged")

    @modlogs.group()
    async def message(self, ctx):
        """
        logs message <edit/delete> [on/off]
        """
        pass

    @message.command("edit")
    @ensure_logging()
    @check_editor()
    async def msgedit(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users leaving your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.message_edit = enabled
            await state.save()

            return await ctx.send(f"message editing will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"message editing is{' not' if not state.message_edit else ''} being logged")

    @message.command("delete")
    @ensure_logging()
    @check_editor()
    async def msgdlt(self, ctx, enabled: bool = None):
        """
        enable/disable logging for users leaving your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.message_delete = enabled
            await state.save()

            return await ctx.send(f"message deleting will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"message deleting is{' not' if not state.message_delete else ''} being logged")

    @modlogs.group()
    async def channel(self, ctx):
        """
        logs channel <create/edit/delete> [on/off]
        """
        pass

    @channel.command("create")
    @ensure_logging()
    @check_editor()
    async def chnlcreate(self, ctx, enabled: bool = None):
        """
        enable/disable logging for channels being created in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.channel_create = enabled
            await state.save()

            return await ctx.send(f"channel creation will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"channel creation is{' not' if not state.channel_create else ''} being logged")

    @channel.command("edit")
    @ensure_logging()
    @check_editor()
    async def chnledit(self, ctx, enabled: bool = None):
        """
        enable/disable logging for channels being edited in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.channel_edit = enabled
            await state.save()

            return await ctx.send(f"channel edits will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"channel edits are{' not' if not state.channel_edit else ''} being logged")

    @channel.command("delete")
    @ensure_logging()
    @check_editor()
    async def chnldelete(self, ctx, enabled: bool = None):
        """
        enable/disable logging for channels being deleted in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.channel_delete = enabled
            await state.save()

            return await ctx.send(f"channel deletion will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"channel deletion is{' not' if not state.channel_delete else ''} being logged")

    @modlogs.group(aliases=['roles'])
    async def role(self, ctx):
        pass

    @role.command("create")
    @ensure_logging()
    @check_editor()
    async def rlcreate(self, ctx, enabled: bool = None):
        """
        enable/disable logging for roles being created in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.role_create = enabled
            await state.save()

            return await ctx.send(f"role creation will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"role creation is{' not' if not state.role_create else ''} being logged")

    @role.command("delete")
    @ensure_logging()
    @check_editor()
    async def rldelete(self, ctx, enabled: bool = None):
        """
        enable/disable logging for roles being deleted in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.role_delete = enabled
            await state.save()

            return await ctx.send(f"role deletion will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"role deletion is{' not' if not state.role_delete else ''} being logged")

    @role.command("edit")
    @ensure_logging()
    @check_editor()
    async def rledit(self, ctx, enabled: bool = None):
        """
        enable/disable logging for roles being edited in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.role_edit = enabled
            await state.save()

            return await ctx.send(f"role edits will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"role edits are{' not' if not state.role_edit else ''} being logged")

    @modlogs.command()
    @ensure_logging()
    @check_editor()
    async def emojis(self, ctx, enabled: bool = None):
        """
        enable/disable logging for emojis being updated in your server
        """
        state = self.cache[ctx.guild.id]  # type: objects.LoggingFlags

        if enabled is not None:
            state.emojis_update = enabled
            await state.save()

            return await ctx.send(f"emoji updates will {'now' if enabled else 'no longer'} be logged")

        await ctx.send(f"emoji updates are{' not' if not state.emojis_update else ''} being logged")
