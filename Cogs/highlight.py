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
        self.db = bot.pg
        self.cache = bot.highlight_cache
        self.bot.loop.create_task(self.build_full_cache())

    def format_message(self, cont: str):
        if len(cont) > 100:
            cont = cont[0:100] + "..."
        return cont

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
        conn = await self.db.acquire()
        for i in self.bot.guilds:
            self.cache[i.id] = await self.build_guild_cache(i, conn=conn)
            if not self.cache[i.id]:
                del self.cache[i.id]

    async def build_guild_cache(self, guild: commands.Guild, conn=None):
        if conn is None:
            connection = await self.db.acquire()
        else:
            connection = conn

        hl = await connection.fetch("SELECT user_id, word FROM highlights WHERE guild_id = $1", guild.id)
        blocks = await connection.fetch("SELECT user_id, rcid, rc FROM hl_blocks WHERE guild_id = $1", guild.id)

        if conn is None:
            await self.db.release(connection)

        din = {}
        dout = {}
        for rec in hl:
            uid = rec['user_id']
            word = rec['word']
            if uid in din:
                din[uid]['words'].append(word)
            else:
                din[uid] = {"words": [word], "blocks": []}

        for rec in blocks:
            uid = rec['user_id']
            cmid = rec['rcid']
            mc = rec['rc']
            if uid in din:
                din[uid]['blocks'].append((cmid, mc))
            else:
                din[uid] = {"words": [], "blocks": [(cmid, mc)]}

        for uid, v in din.items():
            if not v['words']:
                continue

            dout[uid] = (self.build_re(v['words']), v['blocks'])

        return dout

    async def rebuild_single_cache(self, member:commands.Member, conn=None):
        guild = member.guild
        if conn is None:
            connection = await self.db.acquire()
        else:
            connection = conn

        hl = await connection.fetch("SELECT word FROM highlights WHERE guild_id = $1 AND user_id = $2", guild.id, member.id)
        blocks = await connection.fetch("SELECT rcid, rc FROM hl_blocks WHERE guild_id = $1 AND user_id = $2", guild.id, member.id)

        if conn is None:
            await self.db.release(connection)

        b = []
        for i in blocks:
            b.append((i['rcid'], i['rc']))

        h = []
        for i in hl:
            h.append(i['word'])

        if not h:
            if member.id in self.cache[member.guild.id]:
                del self.cache[member.guild.id][member.id]

        if member.guild.id not in self.cache:
            self.cache[member.guild.id] = {}

        if not h:
            if member.id in self.cache[guild.id]:
                del self.cache[guild.id][member.id]

            return

        self.cache[guild.id][member.id] = (self.build_re(h), b)

    @commands.Cog.listener()
    async def on_message(self, msg: commands.Message):
        if not msg.guild or msg.author.bot or msg.guild.id not in self.cache:
            return

        highlighted = []
        for mid, m in self.cache[msg.guild.id].items():
            if mid in highlighted:
                continue

            if msg.channel.id in [x[0] for x in m[1] if x[1] is 1]:
                continue

            if msg.author.id in [x[0] for x in m[1] if x[1] is 0]:
                continue

            v = m[0].search(msg.content)
            if v:
                highlighted.append(mid)
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
    async def add(self, ctx, word: commands.clean_content(escape_markdown=True, fix_channel_mentions=True)):
        """
        add a word to trigger highlights
        """
        if len(word) < 3:
            return await ctx.send("Word is too small")

        async with self.db.acquire() as conn:
            existing = await conn.fetch("SELECT * FROM highlights WHERE guild_id = $1 AND user_id = $2;", ctx.guild.id, ctx.author.id)
            if len(existing) >= 10:
                await ctx.send("You have too many word on highlight")

            else:
                await conn.execute("INSERT INTO highlights VALUES ($1,$2,$3);", ctx.guild.id, ctx.author.id, word)

        await self.rebuild_single_cache(ctx.author)
        await ctx.send(f"added `{word}` to your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def clear(self, ctx):
        """
        clears your highlight triggers and blocks. this is not reversible
        """
        async with self.db.acquire() as conn:
            await conn.execute("DELETE FROM highlights WHERE guild_id = $1 AND user_id = $2;", ctx.guild.id, ctx.author.id)
            await conn.execute("DELETE FROM hl_blocks WHERE guild_id = $1 AND user_id $2;", ctx.guild.id, ctx.author.id)

        if ctx.guild.id in self.cache and ctx.author.id in self.cache[ctx.guild.id]:
            del self.cache[ctx.guild.id][ctx.author.id]

        await ctx.send("cleared your highlight triggers and blocks")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def remove(self, ctx, word: commands.clean_content(escape_markdown=True, fix_channel_mentions=True)):
        """
        remove a word from your highlights
        """
        async with self.db.acquire() as conn:
            await conn.execute("DELETE FROM highlights WHERE guild_id = $1 AND user_id = $2 AND word = $3;", ctx.guild.id, ctx.author.id, word)
            await self.rebuild_single_cache(ctx.author, conn=conn)

        await ctx.send(f"Updated your highlight triggers")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def block(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        block a user or a channel from triggering highlights for you
        """
        async with self.db.acquire() as conn:
            await conn.execute("INSERT INTO hl_blocks VALUES ($1,$2,$3,$4);", ctx.guild.id, ctx.author.id, channel_or_person.id, 0 if isinstance(channel_or_person, commands.User) else 1)
            await self.rebuild_single_cache(ctx.author, conn=conn)

        await ctx.send(f"added {channel_or_person} to your block list")

    @highlight.command()
    @commands.guild_only()
    @commands.check_module("highlight")
    async def unblock(self, ctx, channel_or_person: typing.Union[commands.User, commands.TextChannel]):
        """
        unblocks a user or channel from your highlights, allowing the pings to flow free once again
        """
        await self.db.execute("DELETE FROM hl_blocks WHERE guild_id = $1 AND user_id = $2 AND rcid = $3;", ctx.guild.id, ctx.author.id, channel_or_person.id)
        await self.rebuild_single_cache(ctx.author)
        await ctx.send(f"updated your block list")

    @highlight.command(aliases=['import'])
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
                if i.name.lower() == guild.lower():
                    guild = i
                    break

            if isinstance(guild, str):
                return await ctx.send("Server not found")

        else:
            guild = self.bot.get_guild(guild)

        v = await self.db.fetch("SELECT word FROM highlights WHERE guild_id = $1 AND user_id = $2", guild.id, ctx.author.id)
        if not v:
            return await ctx.send("You have no highlight words in that server!")

        v = [(ctx.guild.id, ctx.author.id, record['word']) for record in v]

        await self.db.executemany("INSERT INTO highlights VALUES ($1,$2,$3);", v)
        await ctx.send("Imported highlight triggers from "+guild.name)

    @highlight.command(aliases=['list'])
    @commands.guild_only()
    @commands.check_module("highlight")
    async def show(self, ctx):
        """
        shows your highlight triggers from this server
        """
        v = await self.db.fetch("SELECT word FROM highlights WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, ctx.author.id)
        if not v:
            return await ctx.send("You have no highlight triggers set up!")
        r = ""
        for record in v:
            r += record['word']+"\n"

        await ctx.send(embed=ctx.embed_invis(description=r))
