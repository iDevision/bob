import argparse
import calendar
import datetime
import time
import uuid
from collections import Counter

import discord
from discord.ext import tasks

from utils import btime, db, errors, commands, argparse as parse
from utils.checks import *


def setup(bot):
    bot.add_cog(community(bot))

def check_giveaway(module="giveaway"):
    return check_module(module)


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

class community(commands.Cog):
    """
    this module allows for interaction with the community.
    useful for things like asking your server questions.
    """
    category = "community"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("community")
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    @commands.command()
    @check_manager()
    @check_module("community")
    async def poll(self, ctx, *, data: str = None):
        """
        creates a poll that allows your community to vote on whatever you are polling!
        requires the `Community Manager` role

        to create a poll, use the following format:
        ```
        !poll --title MyTitle --desc this is for a test --add :MyEmoji: - blue is better --add :MyOtherEmoji: - red is better
        +timer 1m
        ```
        all fields are optional. one field per line. you may add as many emojis as you wish. for info on the timer formatting, see the ``!help time`` command."
        """
        if not data:
            await ctx.send_help(ctx.command)
            return
        pdb = {"queries": {}, "end": 0, "endtxt": "", "title": "", "desc": "",
        "channel": ctx.channel.id, "msg": None}
        parser = Arguments()
        parser.add_argument("--title", "-t", nargs="+")
        parser.add_argument("--add", "-a", "--append", nargs="+", action="append")
        parser.add_argument("--timer", "-timer", nargs="+")
        parser.add_argument("--description", "--desc", "-d", nargs="+")
        try:
            parsed = parser.parse_args(parse.split(data))
        except Exception as e:
            return await ctx.send(str(e))
        if not parsed.add:
            return await ctx.send(f"No options passed!")
        for i in parsed.add:
            i = i[0]
            c = i.split()
            emoji = c[0]
            r = " ".join(c[1:])
            try:
                emoji = await commands.EmojiConverter().convert(ctx, emoji)
            except commands.BadArgument:
                if ":" in emoji:
                    return await ctx.send("unusable emoji!")
            pdb['queries'][emoji] = r
        if parsed.timer:
            c = btime.FutureTime(" ".join(parsed.timer))
            end = btime.human_timedelta(c.dt, brief=True)
            pdb['endtxt'] = end
            pdb['end'] = round(c.dt.timestamp())
        if parsed.description:
            pdb['desc'] = " ".join(parsed.description)
        if parsed.title:
            pdb['title'] = " ".join(parsed.title)
        e = discord.Embed()
        if pdb['end'] != 0 and pdb['desc']:
            e.description = pdb['desc'] + f"\n*poll will close after* "+pdb['endtxt']
        elif pdb['end'] != 0:
            e.description = f"*poll will close after* {pdb['endtxt']}"
        e.colour = discord.Color.purple()
        e.title = pdb['title']
        e.timestamp = datetime.datetime.utcnow()
        for emoji, desc in pdb['queries'].items():
            try:
                emoj = str(self.bot.get_emoji(int(emoji)))
            except:
                emoj = emoji
            e.add_field(name=desc, value=f"*react with* {emoj}", inline=False)
        v = await ctx.send(embed=e)
        pdb['msg'] = v.id
        id = str(uuid.uuid4())
        if pdb['end'] != 0:
            await self.db.execute("INSERT INTO polls "
                                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                      (ctx.guild.id, id, pdb['end'], pdb['endtxt'], pdb['title'], pdb['desc'], pdb['channel'], pdb['msg']))
            for emoji, desc in pdb['queries'].items():
                await self.db.execute("INSERT INTO poll_nodes VALUES (?, ?, ?, ?)",
                                          (ctx.guild.id, id, str(emoji.id), desc))
        for emote in pdb['queries'].keys():
            try:
                r = self.bot.get_emoji(int(emote))
            except Exception:
                r = emote
            await v.add_reaction(r)


    @tasks.loop(seconds=5)
    async def poll_loop(self):
        if not self.bot.is_ready():
            return
        v = await self.db.fetchall("SELECT * FROM polls")
        for guild_id, poll_id, end, endtext, title, description, channel, msgid in v:
            end = int(end)
            try:
                now = calendar.timegm(time.gmtime(time.time()))
                if now >= end:
                    queries = await self.db.fetchall("SELECT emoji, description FROM poll_nodes WHERE poll_id IS ?", poll_id)
                    queried_emojis = []
                    counts = Counter()
                    for record in queries:
                        emoji = record[0]
                        counts[emoji] = 0
                        try:
                            queried_emojis.append(self.bot.get_emoji(int(emoji)))
                        except:
                            queried_emojis.append(emoji)
                    guild = self.bot.get_guild(guild_id)
                    channel = guild.get_channel(channel)
                    msg = await channel.fetch_message(msgid)
                    reactions = msg.reactions
                    for reaction in reactions:
                        if reaction.emoji in queried_emojis:
                            counts[str(reaction.emoji)] = reaction.count - 1 # remove the bot
                    winner = counts.most_common(1)

                    nodes = ""
                    for record in queries:
                        emoji_id = record[0]
                        desc = record[1]
                        try:
                            emoj = str(self.bot.get_emoji(int(emoji_id)))
                        except:
                            emoj = emoji_id
                        nodes += f"{str(emoj)}: {desc}\n"
                    nodes = nodes.strip()
                    e = discord.Embed(title="**Poll:** "+title, description=description)
                    e.colour = discord.Color.green()
                    e.timestamp = datetime.datetime.utcnow()
                    e.add_field(name="The Poll has Closed!", value="options were:\n"+nodes)
                    if not winner:
                        e.add_field(name="Winner:", value="There was no winner!")
                    else:
                        winner = winner[0]
                        try:
                            emoj = str(self.bot.get_emoji(int(winner[0])))
                        except:
                            emoj = winner[0]
                        e.add_field(name="Winner:", value=f"{emoj} with {winner[1]} votes!")
                    await msg.edit(embed=e)
                    #this is safe to do because the poll id is never touched by the users. its simply a uuid.
                    await self.db.connection.executescript(f"DELETE FROM polls WHERE poll_id IS '{poll_id}'; "
                                              f"DELETE FROM poll_nodes WHERE poll_id IS '{poll_id}';--")
            except Exception as e:
                import traceback
                traceback.print_exception(e.__class__, e, e.__traceback__)

    @commands.command("enter")
    @check_giveaway()
    async def enter_gw(self, ctx):
        """
        allows you to enter the giveaway, if one has been set up.
        """
        pointscog = self.bot.get_cog("points")
        if pointscog is None:
            return await ctx.send("this function is currently unavailable.")
        req = await self.db.fetch("SELECT required_points FROM giveaway_settings WHERE guild_id IS ?", ctx.guild.id)
        if req is None:
            await self.db.execute("INSERT INTO giveaway_settings VALUES (?,3000,0,0)", ctx.guild.id)
            raise errors.ModuleDisabled("giveaway")
        enabled = self.bot.guild_module_states[ctx.guild.id]['giveaway']
        if not enabled:
            return
        points = pointscog.cache[ctx.guild.id][ctx.author.id]['points']
        if points < req:
            return await ctx.send("not enough points!")
        cur = await self.db.fetch("SELECT times FROM giveaway_entries WHERE guild_id IS ? AND user_id IS ?", ctx.guild.id, ctx.author.id)
        if cur is None:
            await self.db.execute("INSERT INTO giveaway_entries VALUES (?,?,?)", ctx.guild.id, ctx.author.id, 1)
        else:
            await self.db.execute("UPDATE giveaway_entries VALUES SET times=? WHERE guild_id IS ? AND user_id IS ?", cur+1, ctx.guild.id, ctx.autho.id)
        await ctx.send("entered in giveaway!")

    @commands.command()
    @check_moderator()
    async def purify(self, ctx: commands.Context):
        """
        removeth thy messages!
        requires the `Community Manager` role.
        gets rid of bobs messages.
        """
        def me(msg):
            return msg.author == self.bot.user
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.channel.purge(check=me)
        else:
            await ctx.channel.purge(check=me, bulk=False)

    @commands.group(usage="[subcomands]")
    @check_manager()
    async def giveaway(self, ctx):
        """
        allows you to set up a giveaway.
        requires the `Community Manager` role to use this group of commands
        use `!module giveaway` to enable this module.
        """
        pass

    @giveaway.command()
    @check_giveaway()
    @check_manager()
    async def minpoints(self, ctx, amo: int):
        await self.db.execute("UPDATE giveaway_settings SET required_points=? WHERE guild_id IS ?",
                              amo, ctx.guild.id)
        await ctx.send(f"set the required points to {amo}")

    @giveaway.command("enter")
    @check_giveaway()
    async def enter_gw_2(self, ctx):
        """
        allows you to enter the giveaway, if one has been set up.
        """
        com = ctx.bot.get_command("enter")
        await ctx.invoke(com)

    @giveaway.command("remove", usage="<target>")
    @check_giveaway()
    @check_manager()
    async def gwremove(self, ctx, user: discord.Member):
        """
        removes a user from the giveaway
        """
        await self.db.execute("REMOVE FROM giveaway_entries WHERE guild_id IS ? AND user_id IS ?", ctx.guild.id, user.id)
        await ctx.send(f"removed {user} from the giveaway, if they were in it")

    @giveaway.command(usage="(no parameters)")
    @check_giveaway()
    @check_manager()
    async def entries(self, ctx):
        """
        allows you to see who has entered in the giveaway
        """
        data = await (await self.db.execute("SELECT user_id, times FROM giveaway_entries WHERE guild_id IS ?", ctx.guild.id)).fetchall()
        if not data:
            await ctx.send("no data")
            return
        from collections import Counter
        entries = Counter()
        dels = []
        for id, amo in data:
            try:
                entries[str(ctx.guild.get_member(id))] = amo
            except:
                dels.append(id)
        if dels:
            await self.db.connection.executemany("DELETE FROM giveaway_entries WHERE guild_id IS %i AND user_id IS ?"%ctx.guild.id, [(id,) for id in dels])
        e = discord.Embed()
        e.colour = discord.Color.teal()
        v = ""
        for name, amo in entries.most_common():
            v += "``" + name + "`` with ``" + str(amo) + "`` entries\n"
        if not v:
            v = "[no users]"
        e.add_field(name="entries:", value=v)
        await ctx.send(embed=e)

    @giveaway.command()
    @check_giveaway()
    @check_manager()
    async def addentry(self, ctx, person: discord.Member):
        """
        allows a community manager to enter someone into the database
        """
        exists = await self.db.fetchrow("SELECT times FROM giveaway_entries WHERE guild_id IS ? AND user_id IS ?",
                                            (ctx.guild.id, person.id))
        if exists:
            new = exists[0]+1
            await self.db.execute("UPDATE giveaway_entries SET times=? WHERE guild_id IS ? AND user_id IS ?",
                                      new, ctx.guild.id, person.id)
        else:
            await self.db.execute("INSERT INTO giveaway_entries VALUES (?,?,?)", ctx.guild.id, person.id, 1)
        await ctx.send(f"added {person} into the giveaway")

