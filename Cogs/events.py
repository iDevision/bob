import argparse
import datetime
import json
import shlex

from discord.ext.commands.converter import ColourConverter

from utils import db, commands, checks


def setup(bot):
    bot.add_cog(_events_node(bot))

class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)

def parse_data(s: str, member: commands.Member):
    s = s.replace('{user.name}', member.name).replace('{user.display}', member.display_name).replace('{user.id}', str(member.id))
    s = s.replace('{user.discrim}', member.discriminator).replace('{user.mention}', member.mention.replace("!", ""))
    return s

class _events_node(commands.Cog):
    """
    create a custom welcome/leave message for your server! messages can be embeds or normal messages.
    requires the `Community Manager` role or higher.
    """
    category = "settings"

    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("events")

    @checks.check_module('events')
    @checks.check_manager()
    @commands.group(brief = "see `help events`")
    async def events(self, ctx):
        """
        create a custom welcome/leave message for your server! messages can be embeds or normal messages.
        requires the `Community Manager` role or higher.
        """
        pass

    @events.group(invoke_without_command=True)
    @checks.check_manager()
    @checks.check_module('events')
    async def join(self, ctx, *, message=None):
        """
        Set a message for when people join your server!
        This has 2 ways of working; you can use an embed or plain text.
        to use an embed, prefix your parameters with `embed`
        when using an embed, there are several options.
        --title : set the embed title. note that markdown and mentions dont work here
        --description : set the embed description
        --footer : set the footer text. note that markdown and mentions dont work here
        --color : set the embed color.

        there are also several parameters for the target person. these can be used regardless of the embed state
        - {user.name} : the users name
        - {user.display} : the users display name. this could be their name, or their nickame if they have one.
        - {user.id} : the users ID
        - {user.discrim} : the users discriminator. #0001 etc.
        - {user.mention} : mentions the user.

        Ex. !events join embed --title {user.mention} has joined! --color blue
        """
        prev = await self.db.fetchrow("SELECT member_join, member_join_msg FROM events WHERE guild_id IS ?", ctx.guild.id)
        if prev is not None and message is None:
            d = json.loads(prev[1].replace('𒆙', "'"))
            if d['embed']:
                e = commands.Embed().from_dict(d)
                await ctx.send(f"set to channel: <#{prev[0]}>", embed=e)
            else:
                await ctx.send(f"set to channel: <#{prev[0]}>. msg: {prev[1]}")

        elif prev is None and message is None:
            return await ctx.send(f"No message set up")

        elif message:
            if message.startswith('embed'):
                pred = await self.parser(ctx, message)
            else:
                pred = parse_data(message, ctx.author)
                await ctx.send("`Here's an example of your welcome message:`\n"+pred)
                pred = json.dumps({"embed": False, "text": pred})
            if prev is not None:
                await self.db.execute("UPDATE events SET member_join_msg=? WHERE guild_id IS ?", pred.replace("'", "𒆙"), ctx.guild.id)
            else:
                await self.db.execute("INSERT INTO events VALUES (?,1,?,0,'')", ctx.guild.id, pred.replace("'", "𒆙"))

    @join.group(invoke_without_command=True)
    @checks.check_manager()
    @checks.check_module('events')
    async def channel(self, ctx, channel: commands.TextChannel):
        """
        sets the channel for the welcome message to go to. alternatively, type `remove` to remove the channel
        """
        prev = await self.db.fetchrow("SELECT * FROM events WHERE guild_id IS ?", ctx.guild.id)
        if prev is None:
            return await ctx.send("you need to set up a message to set a channel")
        await self.db.execute("UPDATE events SET member_join=? WHERE guild_id IS ?", channel.id, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> set the join message channel to {channel.mention}")

    @channel.command(hidden=True)
    @checks.check_module('events')
    @checks.check_manager()
    async def remove(self, ctx):
        prev = await self.db.fetchrow("SELECT * FROM events WHERE guild_id IS ?", ctx.guild.id)
        if prev is None:
            return await ctx.send("you need to set up a message to set a channel")
        await self.db.execute("UPDATE events SET member_join=? WHERE guild_id IS ?", 0, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> removed join channel message")

    async def parser(self, ctx, message, parse_variables=True):
        message = message.replace('embed', "")
        message = message.strip()
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument("--color", "-c", "--colour", nargs="+")
        parser.add_argument("--title", "-t", nargs="+")
        parser.add_argument("--description", "-d", nargs="+")
        parser.add_argument("--footer", "-f", nargs="+")
        try:
            args = parser.parse_args(shlex.split(message))
        except Exception as e:
            return await ctx.send(str(e))
        e = commands.Embed()
        if args.color:
            e.colour = await ColourConverter().convert(ctx, args.color[0])
        if args.title:
            e.title = " ".join(args.title)
        if args.description:
            args.description = " ".join(args.description)
            e.description = args.description
        if args.footer:
            e.set_footer(text=" ".join(args.footer))
        if not parse_variables:
            return e.to_dict()
        e2 = self.parse_embed(e.copy(), ctx.author)
        await ctx.send("Heres an example of your welcome message", embed=e2)
        d = e.to_dict()
        d['embed'] = True
        return json.dumps(d)

    def parse_embed(self, e, member):
        if e.description:
            e.description = parse_data(e.description, member)
        if e.title:
            e.title = parse_data(e.title, member)
        if not hasattr(e, "_footer"):
            e._footer = {}
        e._footer['icon_url'] = str(member.guild.icon_url)
        if 'text' in e._footer:
            e._footer['text'] = parse_data(e._footer['text'], member)
        e.set_author(name=str(member), icon_url=member.avatar_url)
        e.timestamp = datetime.datetime.utcnow()
        return e

    @events.group(invoke_without_command=True)
    @checks.check_manager()
    @checks.check_module('events')
    async def leave(self, ctx, *, message=None):
        """
        Set a message for when people leave your server!
        This has 2 ways of working; you can use an embed or plain text.
        to use an embed, prefix your parameters with `embed`
        when using an embed, there are several options.
        --title : set the embed title. note that markdown and mentions dont work here
        --description : set the embed description
        --footer : set the footer text. note that markdown and mentions dont work here
        --color : set the embed color.

        there are also several parameters for the target person. these can be used regardless of the embed state
        - {user.name} : the users name
        - {user.display} : the users display name. this could be their name, or their nickame if they have one.
        - {user.id} : the users ID
        - {user.discrim} : the users discriminator. #0001 etc.
        - {user.mention} : mentions the user.

        Ex. !events leave embed --title {user.mention} has joined! --color blue
        """
        prev = await self.db.fetchrow("SELECT member_leave, member_leave_msg FROM events WHERE guild_id IS ?",
                                      ctx.guild.id)
        if prev is not None and message is None:
            d = json.loads(prev[1])
            if d['type'] == "embed":
                e = commands.Embed().from_dict(d)
                await ctx.send(f"set to channel: <#{prev[0]}>", embed=e)
            else:
                await ctx.send(f"set to channel: <#{prev[0]}>. msg: {prev[1]}")

        elif prev is None and message is None:
            return await ctx.send(f"No message set up")

        elif message:
            if message.startswith('embed'):
                pred = await self.parser(ctx, message)
            else:
                if message.startswith('embed'):
                    pred = await self.parser(ctx, message)
                else:
                    pred = parse_data(message, ctx.author)
                    await ctx.send("`Here's an example of your leave message:`\n" + pred)
                    pred = json.dumps({"embed": False, "text": pred})
            if prev is not None:
                await self.db.execute("UPDATE events SET member_leave_msg=? WHERE guild_id IS ?",
                                      pred.replace("'", "''"), ctx.guild.id)
            else:
                await self.db.execute("INSERT INTO events VALUES (?,0,'',0,?)", ctx.guild.id,
                                      pred.replace("'", "''"))

    @leave.group("channel", invoke_without_command=True)
    @checks.check_manager()
    @checks.check_module('events')
    async def l_channel(self, ctx, channel: commands.TextChannel):
        """
        sets the channel for the welcome message to go to. alternatively, type `remove` to remove the channel
        """
        prev = await self.db.fetchrow("SELECT * FROM events WHERE guild_id IS ?", ctx.guild.id)
        if prev is None:
            return await ctx.send("you need to set up a message to set a channel")
        await self.db.execute("UPDATE events SET member_leave=? WHERE guild_id IS ?", channel.id, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> set the leave message channel to {channel.mention}")

    @l_channel.command("remove", hidden=True)
    @checks.check_module('events')
    @checks.check_manager()
    async def l_remove(self, ctx):
        prev = await self.db.fetchrow("SELECT * FROM events WHERE guild_id IS ?", ctx.guild.id)
        if prev is None:
            return await ctx.send("you need to set up a message to set a channel")
        await self.db.execute("UPDATE events SET member_leave=? WHERE guild_id IS ?", 0, ctx.guild.id)
        await ctx.send(f"{ctx.author.mention} --> removed leave channel message")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        data = await self.db.fetchrow("SELECT member_join, member_join_msg FROM events WHERE guild_id IS ?", member.guild.id)
        if data is None: return
        chan = self.bot.get_channel(data[0])
        if chan and data[1]:
            d = json.loads(data[1])
            if d['embed']:
                e = commands.Embed().from_dict(d)
                e = self.parse_embed(e, member)
                await chan.send(embed=e)
            else:
                s = parse_data(d['text'], member)
                await chan.send(s)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        data = await self.db.fetchrow("SELECT member_leave, member_leave_msg FROM events WHERE guild_id IS ?",
                                      member.guild.id)
        if data is None: return
        chan = self.bot.get_channel(data[0])
        if chan and data[1]:
            d = json.loads(data[1])
            if d['embed']:
                e = commands.Embed().from_dict(d)
                e = self.parse_embed(e, member)
                await chan.send(embed=e)
            else:
                s = parse_data(d['text'], member)
                await chan.send(s)
