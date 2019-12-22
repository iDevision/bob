from utils import commands, btime
import typing
import datetime
import asyncio

def setup(bot):
    bot.add_cog(_highlight(bot))

class _highlight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    def format_message(self, cont: str):
        v = commands.utils.escape_markdown(cont)
        if len(v) > 100:
            v = v[0:100] + "..."
        return v

    async def assemble_messages(self, trigger_msg: commands.Message, target: commands.User)->list:
        around = trigger_msg.channel.history(limit=9, around=trigger_msg, oldest_first=True)
        ret = []
        async for a in around:
            if a.author == target and (datetime.datetime.utcnow() - a.created_at).total_seconds() <= 60:
                return None
            if a.id == trigger_msg.id:
                ret.append(f"**\[{a.created_at.strftime('%I:%M %p')} UTC - {a.author}\]** : {self.format_message(a.content)}")
            else:
                ret.append(f"\[{a.created_at.strftime('%I:%M %p')} UTC - {a.author}\] : {self.format_message(a.content)}")
        return ret

    async def do_highlight(self, trigger_msg: commands.Message, user: commands.User, trigger: str):
        await asyncio.sleep(10)
        cont = await self.assemble_messages(trigger_msg, user)
        if cont is None:
            return
        assembled = "\n".join(cont)
        emb = commands.Embed(title=f"**{trigger}**", color=0x36393E, timestamp=datetime.datetime.utcnow())
        emb.set_footer(text="highlighted at")
        emb.description = assembled
        emb.add_field(name="To the message!", value=f"[Message]({trigger_msg.jump_url})")
        try:
            await user.send(f"You've been highlighted in {trigger_msg.channel.mention} with trigger word **{trigger}**",embed=emb)
        except:
            pass

    @commands.Cog.listener()
    async def on_message(self, msg: commands.Message):
        if not msg.guild or msg.author.bot: return
        hl = await self.db.fetchall("SELECT user_id, word FROM highlights WHERE guild_id IS ?", msg.guild.id)
        blocks = await self.db.fetchall("SELECT user_id, rcid, rc FROM hl_blocks WHERE guild_id IS ?", msg.guild.id)
        highlighted = []
        for uid, word in hl:
            if uid in highlighted:
                return
            for i in blocks:
                if i['user_id'] == uid:
                    if i['rc'] and i['rcid'] == msg.author: # person
                        highlighted.append(uid) # fake it to save iterations
                        break
                    elif i['rcid'] == msg.channel.id:
                        highlighted.append(uid)
                        break
            if uid in highlighted:
                continue

            if word in msg.content:
                self.bot.loop.create_task(self.do_highlight(msg, self.bot.get_user(uid), word))
                highlighted.append(uid)

    @commands.group(invoke_without_command=True, aliases=["hl"])
    @commands.guild_only()
    @commands.check_module("highlight")
    async def highlight(self, ctx):
        """
        Highlights are essentially pings as normal text.
        you can add words to trigger the highlight and send you a dm when these words are said,
        so you always know when when those other guys are talking about you.
        highlights will not trigger if you have talked within the last minute in that channel, to help you keep your sanity.
        __note__: highlight triggers are per-guild
        """
        pass

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def add(self, ctx, word):
        """
        add a word to trigger highlights
        """
        await self.db.execute("INSERT INTO highlights VALUES (?,?,?)", ctx.guild.id, ctx.author.id, word)
        await ctx.send(f"added `{word}` to your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def remove(self, ctx, word):
        """
        remove a word from your highlights
        """
        await self.db.execute("DELETE FROM highlights WHERE guild_id IS ? AND user_id IS ? AND word IS ?", ctx.guild.id, ctx.author.id, word)
        await ctx.send(f"Updated your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def block(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        block a user or a channel from triggering highlights for you
        """
        await self.db.execute("INSERT INTO hl_blocks (?,?,?,?)", ctx.guild.id, ctx.author.id, channel_or_person.id, 0 if isinstance(channel_or_person, commands.User) else 1)
        await ctx.send(f"added {channel_or_person} to your block list")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def unblock(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        unblocks a user or channel from your highlights, allowing the pings to flow free once again
        """
        await self.db.execute("DELETE FROM hl_blocks WHERE guild_id IS ? AND user_id IS ? AND rcid IS ?", ctx.guild.id, ctx.author.id, channel_or_person.id)
        await ctx.send(f"updated your block list")

    @highlight.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.check_module("highlight")
    async def port(self, ctx, *, guild: typing.Union[int, str]):
        """
        imports your highlight list from another server to the current server.
        you can pass the server's ID or name.
        """
        if isinstance(guild, str):
            for i in self.bot.guilds:
                if i.name.lower() == guild:
                    guild = i
                    break
            if isinstance(guild, str):
                return await ctx.send("Server not found")
        else:
            guild = self.bot.get_guild(guild)

        v = await self.db.fetchall("SELECT word FROM highlights WHERE guild_id IS ? AND user_id IS ?", guild.id, ctx.author.id)
        if not v:
            return await ctx.send("You have no highlight words in that server!")
        v = [(ctx.guild.id, ctx.author.id, s[0]) for s in v]
        await self.db.executemany("INSERT INTO highlights VALUES (?,?,?)", v)
        await ctx.send("Imported highlight triggers from "+guild.name)

    @highlight.command(aliases=['list'])
    @commands.guild_only()
    @commands.check_module("highlight")
    async def show(self, ctx):
        """
        shows your highlight triggers from this server
        """
        v = await self.db.fetchall("SELECT word FROM highlights WHERE guild_id IS ? AND user_id IS ?", ctx.guild.id, ctx.author.id)
        if not v:
            return await ctx.send("You have no highlight triggers set up!")
        r = ""
        for i in v:
            r += i[0]+"\n"
        await ctx.send(embed=ctx.embed_invis(description=r))
