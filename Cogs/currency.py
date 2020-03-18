import asyncio
import collections
import random
import typing

import discord
from discord.ext import tasks

from utils import db, paginator, commands
from utils.checks import *


def setup(bot):
    bot.add_cog(BasicCurrency(bot))


class BasicCurrency(commands.Cog, name="Currency2"):
    category = "currency"
    def __init__(self, bot):
        self.bot = bot
        self.activities = commands.CooldownMapping.from_cooldown(5, 900, commands.BucketType.member)
        self.activity_loop.start()

    def cog_unload(self):
        self.activity_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, msg):
        self.activities.update_rate_limit(msg)

    @tasks.loop(minutes=5)
    async def activity_loop(self):
        local_edits = []
        self.activities._verify_cache_integrity()
        for key, bucket in self.activities._cache.items():
            if bucket._tokens <= 0:
                local_edits.append((key[0], key[1]))
        if local_edits:
            await self.bot.pg.executemany("INSERT INTO talking_stats VALUES ($1,$2,1) ON CONFLICT (guild_id, user_id) DO UPDATE SET messages = talking_stats.messages + 1;", local_edits)
    
    @commands.command()
    async def activity(self, ctx, target: commands.Member = None):
        """
        shows a user's activity on the server. every 5 minutes of activity gives 1 activity point
        """
        target = target or ctx.author
        data = await self.bot.pg.fetchrow("SELECT messages FROM talking_stats WHERE guild_id = $1 AND user_id = $2;", ctx.guild.id, target.id)
        if not data:
            return await ctx.send("No data for this user")
        await ctx.send(f"{target} has {data['messages']} activity points")

class Currency(commands.Cog, name="points"):
    category = "currency"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("currency")
        self.lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.db.execute("DELETE FROM currency WHERE guild_id IS ?", guild.id)

    async def points_for(self, member: commands.Member):
        v = await self.db.fetch("SELECT points FROM currency WHERE guild_id IS ? AND user_id IS ?", member.guild.id, member.id)
        if v is None:
            raise commands.CommandError(f"{member} does not have a currency profile")

    async def set_points_for(self, member: commands.Member, points: int):
        await self.db.execute("UPDATE currency SET points=? WHERE guild_id IS ? AND user_id IS ?", points, member.id)\

    @commands.group("points", invoke_without_command=True, usage="[target]")
    @check_module("currency")
    async def points(self, ctx: commands.Context, target: discord.Member = None):
        """
        alias of profile
        """
        cmd = self.bot.get_command("profile")
        await ctx.invoke(cmd, target)

    @points.command("remove", usage="<target> <amount>")
    @check_manager()
    @check_module("currency")
    async def points_remove(self, ctx, member: discord.Member, amo: int):
        """
        removes points from a user in your guild
        you must have the `community manager` role to use this command
        """
        userpoints = await self.points_for(member)
        if amo > userpoints:
            userpoints = 0
            return await ctx.send(f"{ctx.author.mention} --> {str(member)} didnt have that many points!"
                           f" set their points to 0")
        else:
            userpoints -= amo
            await ctx.send(f"{ctx.author.mention} --> removed {amo} points from {member.display_name}")
        await self.set_points_for(member, userpoints)

    @commands.command(usage="<amount>")
    @check_module("currency")
    async def gamble(self, ctx, amo: int):
        """
        gambles an amount of your points.
        odds of winning are 1/3
        may become customizable at some point
        """
        # TODO: make odds customizable per server?
        if amo > 500:
            return await ctx.send(f"{ctx.author.mention} --> that's too many points! (max 500)")
            return
        if amo < 1:
            return await ctx.send(f"{ctx.author.mention} --> trying to gamble negative points are we?")
        userpoints = await self.points_for(ctx.author)
        if amo > userpoints:
            await ctx.send(f"{ctx.author.mention} --> you don't have that many points!")
            return

        rnd = random.randint(0, 3)
        if rnd == 2:
            diff = round(amo * 0.5)
            await ctx.send(f"{ctx.author.mention} gambled {amo} points and gained an extra {diff} points!")
            userpoints += diff
        else:
            userpoints -= amo
            await ctx.send(f"{ctx.author.mention} gambled {amo} points and lost them!")
        await self.set_points_for(ctx.author, userpoints)

    @points.command(usage="<target> <amount>")
    @check_module("currency")
    async def donate(self, ctx, target: discord.Member, amo: int):
        """
        feeling generous? use this command to give some of your points to another person!
        """
        if target == ctx.author:
            return await ctx.send(f"well that's pointless")
        apoints = await self.points_for(ctx.author)
        bpoints = await self.points_for(target)
        if amo > apoints:
            return await ctx.send(f"you don't have that many points!")
        if amo < 1:
            return await ctx.send(f"well that's pointless")
        await self.set_points_for(target, bpoints+amo)
        await self.set_points_for(ctx.author, apoints-amo)
        await ctx.send(f"{ctx.author.mention} gave {str(amo)} points to {target.display_name}")

    @points.command(usage="<target> <amount>")
    @check_manager()
    @check_module("currency")
    async def add(self, ctx, target: typing.Union[discord.Member, str], amo: int):
        """
        Adds points to a member
        you need the Community Manager role to use this command
        """
        if isinstance(target, discord.Member):
            await self.db.execute("UPDATE currency SET points = points + ? WHERE guild_id IS ? AND user_id IS ?", amo, ctx.guild.id, target.id)
            await ctx.send(f"{ctx.author.mention} --> added {amo} points to {target}")
        else:
            if target.startswith("*"):
                targ = target.lstrip("*")
                if targ == "all":
                    await self.db.execute("UPDATE currency SET points = points + ? WHERE guild_id IS ?", amo, ctx.guild.id)
                    await ctx.send(f"added {amo} points to the entire server")

    @commands.command("leaderboard")
    @check_module("currency")
    async def top_points(self, ctx):
        tops = collections.Counter()
        for uid in self.cache[ctx.guild.id]:
            warns = self.cache[ctx.guild.id][uid]['points']
            mem = ctx.guild.get_member(uid)
            tops[str(mem)] = warns
        data = tops.most_common(50)
        if not data:
            return await ctx.send("No points data")
        pages = paginator.FieldPages(ctx, entries=data, per_page=5, embed_color=discord.Color.red())
        await pages.paginate()
