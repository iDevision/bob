# kudos to lambda for helping me with this

from utils import commands, btime
import typing
import datetime
import asyncio
import re

def setup(bot):
    bot.add_cog(_highlight(bot))

class _highlight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.cache = bot.highlight_cache
        self.bot.loop.create_task(self.build_full_cache())

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

    def build_re(self, highlights):
        return re.compile((
                              r'(?i)'  # case insensitive
                              r'\b'  # word bound
                              r'(?:{})'  # non capturing group, to make sure that the word bound occurs before/after all words
                              r'\b'
                          ).format('|'.join(map(re.escape, highlights))))

    async def build_full_cache(self):
        await self.bot.wait_until_ready()
        for i in self.bot.guilds:
            self.cache[i.id] = await self.build_guild_cache(i)

    async def build_guild_cache(self, guild: commands.Guild):
        hl = await self.db.fetchall("SELECT user_id, word FROM highlights WHERE guild_id IS ?", guild.id)
        blocks = await self.db.fetchall("SELECT user_id, rcid, rc FROM hl_blocks WHERE guild_id IS ?", guild.id)
        din = {}
        dout = {}
        for uid, word in hl:
            if uid in din:
                din[uid]['words'].append(word)
            else:
                din[uid] = {"words": [word], "blocks": []}
        for uid, cmid, mc in blocks:
            if uid in din:
                din[uid]['blocks'].append((cmid, mc))
            else:
                din[uid] = {"words": [], "blocks": [(cmid, mc)]}
        for uid, v in din.items():
            dout[uid] = (self.build_re(v['words']), v['blocks'])
        return dout

    async def rebuild_single_cache(self, member:commands.Member):
        guild = member.guild
        hl = await self.db.fetchall("SELECT word FROM highlights WHERE guild_id IS ? AND user_id IS ?", guild.id, member.id)
        blocks = await self.db.fetchall("SELECT rcid, rc FROM hl_blocks WHERE guild_id IS ? AND user_id IS ?", guild.id, member.id)
        b = []
        for i in blocks:
            b.append((i[0], i[1]))
        h = []
        for i in hl:
            h.append(i[0])
        if not h:
            if member.id in self.cache[guild.id]:
                del self.cache[guild.id][member.id]
            return
        self.cache[guild.id][member.id] = (self.build_re(h), b)

    @commands.Cog.listener()
    async def on_message(self, msg: commands.Message):
        if not msg.guild or msg.author.bot or msg.guild.id not in self.cache: return
        highlighted = []
        for mid, m in self.cache[msg.guild.id].items():
            if (msg.author, 0) in m[1] or (msg.channel.id, 1) in m[1]:
                continue
            v = m[0].search(msg.content)
            if v:
                self.bot.loop.create_task(self.do_highlight(msg, msg.guild.get_member(mid), v.group()))

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
        await self.rebuild_single_cache(ctx.author)
        await ctx.send(f"added `{word}` to your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def remove(self, ctx, word):
        """
        remove a word from your highlights
        """
        await self.db.execute("DELETE FROM highlights WHERE guild_id IS ? AND user_id IS ? AND word IS ?", ctx.guild.id, ctx.author.id, word)
        await self.rebuild_single_cache(ctx.author)
        await ctx.send(f"Updated your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def block(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        block a user or a channel from triggering highlights for you
        """
        await self.db.execute("INSERT INTO hl_blocks (?,?,?,?)", ctx.guild.id, ctx.author.id, channel_or_person.id, 0 if isinstance(channel_or_person, commands.User) else 1)
        await self.rebuild_single_cache(ctx.author)
        await ctx.send(f"added {channel_or_person} to your block list")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def unblock(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        unblocks a user or channel from your highlights, allowing the pings to flow free once again
        """
        await self.db.execute("DELETE FROM hl_blocks WHERE guild_id IS ? AND user_id IS ? AND rcid IS ?", ctx.guild.id, ctx.author.id, channel_or_person.id)
        await self.rebuild_single_cache(ctx.author)
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
