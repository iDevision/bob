import datetime

import discord

from utils import db, commands, errors
from utils.checks import *


def setup(bot):
    bot.add_cog(_modlogs(bot))

class _modlogs(commands.Cog):
    """
    allows you to edit the `modlogs` module of the bot
    requires the `bot editor` role
    """
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("logs")
        # yes, i have 2 connections to the same database. only one of them is writing data, so it should be ok.

    async def cog_check(self, ctx):
        if not await basic_check(ctx, "editor", "editor"):
            raise MissingRequiredRole("You need the `Bot Editor` role to use this command!")
        if not self.bot.guild_module_states[ctx.guild.id]['modlogs']:
            raise errors.ModuleDisabled("modlogs")
        return True

    @commands.group(invoke_without_command=True, aliases=['logs', 'logger'])
    async def modlogs(self, ctx):
        """
        set up logging for your server.
        you need the `Bot Editor` role to use this category
        """
        await ctx.send_help(ctx.command)

    @modlogs.group("channel", invoke_without_command=True, usage="<channel or 'remove'>")
    async def ms_chan(self, ctx, channel: discord.TextChannel=None):
        """
        set the channel your logs should go to.
        note that some logs may duplicate with the automod logs.
        """
        if not channel:
            e = discord.Embed()
            e.colour = discord.colour.Color.dark_gold()
            channel = await self.db.fetch("SELECT channel FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            channel = self.bot.get_channel(channel)
            if not channel:
                return await ctx.send("invalid or no modlogs channel!")
            e.add_field(name="mod.logs.channel", value=f"{channel.mention}")
            e.timestamp = datetime.datetime.utcnow()
            await ctx.send(embed=e)
            return
        try:
            await self.db.execute("UPDATE modlogs SET channel = ? WHERE guild_id IS ?", channel.id, ctx.guild.id)
        except:
            await self.db.execute("INSERT INTO modlogs VALUES (?,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,?)", ctx.guild.id, channel.id)
        await ctx.send(f"{ctx.author.mention} --> updated ``modlogs.channel`` to {channel.mention}")

    @ms_chan.command()
    async def remove(self, ctx):
        """
        remove the logs channel. effectively stopping logging.
        """
        await self.db.execute("UPDATE modlogs SET channel = 0 WHERE guild_id IS ?", ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> removed modlogs channel")


    @modlogs.command("member_join")
    async def ml_mj(self, ctx, state: bool=None):
        """
        notifies when a member joins. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET member_join=? WHERE guild_id IS ?", int(state), ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``member join`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT member_join FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``member join`` is {bool(state)}")


    @modlogs.command("member_leave")
    async def ml_ml(self, ctx, state: bool=None):
        """
        notifies when a member leaves. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET member_leave=? WHERE guild_id IS ?", int(state),
                                      ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``member leave`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT member_leave FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``member leave`` is {bool(state)}")


    @modlogs.command("member_banned")
    async def ml_mib(self, ctx, state: bool=None):
        """
        notifies when a member is banned. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET member_isbanned=? WHERE guild_id IS ?", int(state),
                                      ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``member isbanned`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT member_isbanned FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``member isbanned`` is {bool(state)}")


    @modlogs.command("member_unbanned")
    async def ml_miub(self, ctx, state: bool=None):
        """
        notifies when a member is unbanned. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET member_isunbanned=? WHERE guild_id IS ?", int(state),
                                      ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``member isunbanned`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT member_leave FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``member isunbanned`` is {bool(state)}")


    @modlogs.command("member_kicked")
    async def ml_mik(self, ctx, state: bool=None):
        """
        notifies when a member is kicked. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET member_iskicked=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``member iskicked`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT member_iskicked FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``member iskicked`` is {bool(state)}")


    @modlogs.command("message_delete")
    async def ml_md(self, ctx, state: bool=None):
        """
        notifies when a message is deleted. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET message_delete=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``message delete`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT message_delete FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``message delete`` is {bool(state)}")


    @modlogs.command("message_edit")
    async def ml_me(self, ctx, state: bool=None):
        """
        notifies when a message is edited. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET message_edit=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``message edit`` to {str(state)}")
        else:
            state = await self.db.execute("SELECT message_edit FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``message edit`` is {bool(state)}")


    @modlogs.command("message_bulk_delete")
    async def ml_mbd(self, ctx, state: bool=None):
        """
        notifies when messages are bulk deleted. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET message_bulk_delete=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``message bulk delete`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT message_bulk_delete FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``message bulk delete`` is {bool(state)}")

    @modlogs.command("role_create")
    async def ml_rc(self, ctx, state: bool=None):
        """
        notifies when a role is created. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET role_create=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``role create`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT role_create FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``role create`` is {bool(state)}")

    @modlogs.command("role_edit")
    async def ml_re(self, ctx, state: bool=None):
        """
        notifies when a role is edited. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET role_edit=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``role edit`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT role_edit FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``role edit`` is {bool(state)}")

    @modlogs.command("role_delete")
    async def ml_rd(self, ctx, state: bool=None):
        """
        notifies when a role is deleted. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET role_delete=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``role delete`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT role_delete FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``role delete`` is {bool(state)}")

    @modlogs.command("channel_create")
    async def ml_cc(self, ctx, state: bool=None):
        """
        notifies when a channel is created. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET channel_create=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``channel create`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT channel_create FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``channel create`` is {bool(state)}")

    @modlogs.command("channel_edit")
    async def ml_ce(self, ctx, state: bool=None):
        """
        notifies when a channel is edited. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET channel_edit=? WHERE guild_id IS ?", int(state),
                                                                                                     ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> set ``channel edit`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT channel_edit FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``channel edit`` is {bool(state)}")

    @modlogs.command("channel_delete")
    async def ml_cd(self, ctx, state: bool=None):
        """
        notifies when a channel is deleted. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET channel_delete=? WHERE guild_id IS ?", (int(state),
                                                                                                     ctx.guild.id))
            await ctx.send(f"{ctx.author.mention} --> set ``channel delete`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT channel_delete FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``channel delete`` is {bool(state)}")

    @modlogs.command("emojis_update")
    async def ml_eu(self, ctx, state: bool=None):
        """
        notifies when the servers emojis are updated. set this to on or off
        """
        if state is not None:
            await self.db.execute("UPDATE modlogs SET emojis_update=? WHERE guild_id IS ?", (int(state),
                                                                                                     ctx.guild.id))
            await ctx.send(f"{ctx.author.mention} --> set ``emojis update`` to {str(state)}")
        else:
            state = await self.db.fetch("SELECT emojis_update FROM modlogs WHERE guild_id IS ?", ctx.guild.id)
            await ctx.send(f"{ctx.author.mention} --> log ``emojis update`` is {bool(state)}")
