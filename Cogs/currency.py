import asyncio
import random
import typing

import discord
from discord.ext import tasks

from utils import paginator, commands
from utils.checks import *


def setup(bot):
    bot.add_cog(Currency(bot))
    bot.add_cog(BasicCurrency(bot))

def check_twitch():
    def predicate(ctx):
        if not ctx.bot.get_from_guildid(ctx.guild.id)[0]:
            raise commands.CommandError("This server is not connected to a twitch account! This command requires a twitch link!")
        return True
    return commands.check(predicate)

class BasicCurrency(commands.Cog, name="Currency2"):
    category = "currency"
    def __init__(self, bot):
        self.bot = bot
        self.activities = commands.CooldownMapping.from_cooldown(5, 300, commands.BucketType.member)
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

class Currency(commands.Cog):
    category = "currency"
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.bridge
        self.lock = asyncio.Lock()
        self.activity = commands.CooldownMapping.from_cooldown(5, 900, commands.BucketType.member)
        self.activity_loop.start({})

    def cog_unload(self):
        self.activity_loop.cancel()

    @tasks.loop(minutes=15)
    async def activity_loop(self, cache: dict):
        edits = []
        local_edits = []
        self.activity._verify_cache_integrity()

        for key, bucket in self.activity._cache.items():
            token, conns = self.bot.get_from_guildid(key[0])
            if token is None:
                if bucket._tokens == 0:
                    local_edits.append((key[0], key[1]))
                continue

            if key[0] not in cache:
                cache[key[0]] = await self.db.fetchval("SELECT discord_activity_points FROM currency_config WHERE user_token = $1", token)

            if bucket._tokens == 0:
                local_edits.append((key[0], key[1]))
                edits.append((key[1], token, cache[key[0]]))

        if edits:
            await self.db.executemany("WITH child AS (SELECT user_token FROM connections WHERE discord_id=$3) UPDATE "
                                  "points_data SET points = points + $1 WHERE parent_token = $2 AND child_token = (select * from child)", edits)

        if local_edits:
            await self.bot.pg.executemany("INSERT INTO talking_stats VALUES ($1,$2,$3) ON CONFLICT (guild_id, user_id) DO UPDATE SET messages = talking_stats.messages + 1;", local_edits)


    async def points_for(self, member: commands.Member, conn=None):
        token, conns = self.bot.get_from_guildid(member.guild.id)
        if not token:
            raise commands.CommandError("Server not connected to twitch")
        conn = conn or self.db
        v = await conn.fetchval("WITH child AS (SELECT user_token FROM connections WHERE discord_id=$2) SELECT points "
                                "FROM points_data WHERE parent_token = $1 AND child_token = (select * from child)", token, member.id)
        if not v:
            raise commands.CommandError(f"{member} does not have a currency profile! please link twitch to the bot using `!link`")
        return v

    async def set_points_for(self, member: commands.Member, points: int, add=False, conn=None)->bool:
        token, conns = self.bot.get_from_guildid(member.guild.id)
        conn = conn or self.db
        v = await conn.fetch(f"WITH child AS (SELECT user_token FROM connections WHERE discord_id=$3) UPDATE "
                                f"points_data SET points{' = points +' if add else '='}$1 WHERE parent_token = $2 AND child_token"
                                f" = (SELECT * FROM child) RETURNING *;", points, token, member.id)
        if not v:
            return False
        return True

    @commands.group("points", invoke_without_command=True, usage="[target]")
    @check_module("currency")
    @check_twitch()
    async def points(self, ctx: commands.Context, target: discord.Member = None):
        """
        """
        target = target or ctx.author

        token, conns = self.bot.get_from_guildid(ctx.guild.id)

        record = await self.db.fetchrow("WITH child AS (SELECT user_token FROM connections WHERE discord_id=$2) SELECT "
                                        "points, hours, currency_name FROM points_data INNER JOIN currency_config ON "
                                        "currency_config.user_token=$1 WHERE parent_token = $1 AND child_token = "
                                        "(select * from child)", token, target.id)

        if record is None:
            return await ctx.send(f"No currency data found for {target}")

        emb = ctx.embed_invis()
        emb.set_author(name=str(target), icon_url=target.avatar_url)
        emb.description = f"{record['currency_name']} - {record['points']}\nHours - {record['hours']}"
        await ctx.send(embed=emb)

    @points.command("remove", usage="<target> <amount>")
    @check_manager()
    @check_module("currency")
    @check_twitch()
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
    @check_twitch()
    async def gamble(self, ctx, amo: int):
        """
        gambles an amount of your points.
        odds of winning are 1/3
        may become customizable at some point
        """
        if amo > 500:
            return await ctx.send(f"{ctx.author.mention} --> that's too many points! (max 500)")
        if amo < 1:
            return await ctx.send(f"{ctx.author.mention} --> trying to gamble negative points are we?")
        token, conns = self.bot.get_from_guildid(ctx.guild.id)
        rec = await self.db.fetchval("WITH child AS "
                                     "(SELECT user_token FROM connections WHERE discord_id=$2) "
                                     "SELECT points, gamble_yield, gamble_chance FROM points_data INNER JOIN "
                                     "currency_config ON currency_config.user_token = points_data.parent_token WHERE "
                                     "parent_token = $1 AND child_token = (SELECT * FROM child)", token, ctx.author.id)
        if not rec['points']:
            return await ctx.send("You do not have a twitch link set up!")
        userpoints = rec['points']
        if amo > userpoints:
            await ctx.send(f"{ctx.author.mention} --> you don't have that many points!")
            return

        rnd = random.randint(1, 100)
        if rnd > rec['gamble_chance']:
            diff = round(amo * (rec['gamble_yield']/100))
            await ctx.send(f"{ctx.author.mention} gambled {amo} points and gained an extra {diff} points!")
            userpoints += diff
        else:
            userpoints -= amo
            await ctx.send(f"{ctx.author.mention} gambled {amo} points and lost them!")
        await self.set_points_for(ctx.author, userpoints)

    @points.command(usage="<target> <amount>")
    @check_module("currency")
    @check_twitch()
    async def donate(self, ctx, target: discord.Member, amo: int):
        """
        feeling generous? use this command to give some of your points to another person!
        """
        if target == ctx.author:
            return await ctx.send(f"well that's pointless")

        token, conns = self.bot.get_from_guildid(ctx.guild.id)
        conn = await self.bot.bridge.acquire()
        apoints = await self.points_for(ctx.author, conn=conn)
        bpoints = await self.points_for(target, conn=conn)

        if amo > apoints:
            return await ctx.send(f"you don't have that many points!")

        if amo < 1:
            return await ctx.send(f"well that's pointless")

        await self.set_points_for(target, bpoints+amo, conn=conn)
        await self.set_points_for(ctx.author, apoints-amo, conn=conn)
        await self.db.release(conn)
        await ctx.send(f"{ctx.author.mention} gave {str(amo)} points to {target.display_name}")

    @points.command(usage="<target> <amount>")
    @check_manager()
    @check_module("currency")
    @check_twitch()
    async def add(self, ctx, target: typing.Union[discord.Member, str], amo: int):
        """
        Adds points to a member
        you need the Community Manager role to use this command
        """
        if isinstance(target, discord.Member):
            await self.db.execute("UPDATE currency SET points += $1 WHERE guild_id IS ? AND user_id IS ?", amo, ctx.guild.id, target.id)
            await ctx.send(f"{ctx.author.mention} --> added {amo} points to {target}")

        else:
            if target.startswith("*"):
                targ = target.lstrip("*")

                if targ == "all":
                    await self.db.execute("UPDATE currency SET points = points + $1 WHERE parent_token=$2", amo, ctx.guild.id)
                    await ctx.send(f"added {amo} points to the entire server")

    @commands.command("leaderboard")
    @check_module("currency")
    @check_twitch()
    async def top_points(self, ctx):
        token, conns = self.bot.get_from_guildid(ctx.guild.id)
        ordered = await self.db.fetch("SELECT discord_id, points FROM points_data INNER JOIN connections ON "
                                      "points_data.child_token = connections.user_token WHERE parent_token=$1 ORDER BY points desc",
                                      token)
        pages = paginator.FieldPages(ctx, entries=[f"{ctx.bot.get_user(rec[0])} - {rec[1]}" for rec in ordered], per_page=5, embed_color=discord.Color.red())
        await pages.paginate()
