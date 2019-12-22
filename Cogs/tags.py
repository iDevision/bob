import asyncio
import datetime
import difflib

import discord

from utils import db, paginator, commands
from utils.checks import basic_check, check_module


def setup(bot):
    bot.add_cog(_tags(bot))


class TagName(commands.clean_content):
    def __init__(self, *, lower=False):
        self.lower = lower
        super().__init__()

    async def convert(self, ctx, argument):
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()

        if not lower:
            raise commands.BadArgument('Missing tag name.')

        if len(lower) > 100:
            raise commands.BadArgument('Tag name is a maximum of 100 characters.')

        first_word, _, _ = lower.partition(' ')

        # get tag command.
        root = ctx.bot.get_command('tag')
        if first_word in root.all_commands:
            raise commands.BadArgument('This tag name starts with a reserved word.')

        return converted if not self.lower else lower


async def has_tag_edit_perm(c, ctx, tag):
    try:
        if await basic_check(ctx, "moderator", "editor"):
            return True
    except: pass
    owner = await c.db.fetch("SELECT owner FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, tag)
    if ctx.author.id == owner:
        return True
    return False


class _tags(commands.Cog):
    category="tags"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("tags")

    @commands.group(aliases=["tags"], invoke_without_command=True)
    @commands.guild_only()
    @check_module('tags')
    async def tag(self, ctx: commands.Context, *, searchtag: TagName = None):
        """
        responds with a tag, if it exists.
        tags can be created by anyone, and used by anyone. they're like custom commands, but public.
        tags can be created with the `tag create` command.
        """
        if searchtag is None:
            return await ctx.send("not enough data")
        match = await self.db.fetchrow("SELECT name, response, uses FROM tags WHERE guild_id IS ? and name IS ?", ctx.guild.id, searchtag)
        if match:
            await ctx.send(match[1])
            await self.db.execute("UPDATE tags SET uses=? WHERE guild_id IS ? AND name IS ?", match[2]+1, ctx.guild.id, match[0])
        else:
            cur = await self.db.execute("SELECT name FROM tags WHERE guild_id IS ?", ctx.guild.id)
            names = await cur.fetchall()
            loop = asyncio.get_running_loop()
            def func():
                return difflib.get_close_matches(searchtag, names, 5)
            names = await loop.run_in_executor(None, func)
            if names:
                e = discord.Embed(color=discord.Colour.from_rgb(54, 57, 62))
                e.title = f"tag not found. maybe you meant one of these?"
                e.description ="``"+ "``\n``".join(names) + "``"
                await ctx.send(embed=e)
                return
            await ctx.send(f"{ctx.author.mention} --> that tag does not exist!")

    @tag.command()
    @commands.guild_only()
    @check_module('tags')
    async def list(self, ctx):
        tags = await self.db.fetchall("SELECT name FROM tags WHERE guild_id IS ?", ctx.guild.id)
        v = [t[0] for t in tags]
        await ctx.paginate(v)

    @tag.command(aliases=["add", "make"], usage="<name> [response]")
    @commands.guild_only()
    @check_module('tags')
    async def create(self, ctx: commands.Context, name: TagName, *, resp: commands.clean_content=None):
        exists = await self.db.fetchrow("SELECT * FROM tags WHERE name IS ? AND guild_id IS ?", name, ctx.guild.id)
        if exists:
            return await ctx.send(f"{ctx.author.mention} --> that tag already exists!")
        if not resp:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            await ctx.send(f"{ctx.author.mention} --> ok, so the tag is named `{name}`. what should the content be?")
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=120)
            except asyncio.TimeoutError:
                return await ctx.send("time limit reached. aborting.")
            if msg.content == ctx.prefix+"cancel":
                return await ctx.send(f"{ctx.author.mention} --> aborting")
            resp = await commands.clean_content().convert(ctx, msg.content)
        await self.db.execute("INSERT INTO tags VALUES (?,?,?,?,?)", ctx.guild.id, name, resp, ctx.author.id, 0)
        await ctx.send(f"{ctx.author.mention} --> created tag {name}")


    @tag.command(aliases=["delete", "rm", "del"], usage="<name>")
    @commands.guild_only()
    @check_module('tags')
    async def remove(self, ctx, name: TagName):
        v = await self.db.fetchrow("SELECT * FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, name)
        if v and await has_tag_edit_perm(self, ctx, name):
            await self.db.execute("DELETE FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, name)
            await ctx.send(f"{ctx.author.mention} --> successfully removed tag `{name}`")
        elif v and not await has_tag_edit_perm(self, ctx, name):
            await ctx.send(f"{ctx.author.mention} --> you cannot delete that tag! It does not belong to you!")
        else:
            await ctx.send(f"{ctx.author.mention} --> that tag does not exist!")


    @tag.command(aliases=["?"], usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def info(self, ctx, name: TagName):
        """
        shows info about a tag.
        this includes things like the owner and how many times the tag has been used.
        """
        data = await self.db.fetchrow("SELECT * FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, name)
        if not data:
            return await ctx.send(f"{ctx.author.mention} --> that tag does not exist!")
        e = discord.Embed(color=discord.Color.blurple())
        e.add_field(name="Owner", value=str(ctx.guild.get_member(data[3])))
        e.add_field(name="Uses", value=data[4])
        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)

    @tag.command(usage="<tag name> <content>")
    @commands.guild_only()
    @check_module('tags')
    async def edit(self, ctx, name: TagName, *, resp: commands.clean_content):
        """
        allows you to edit a tag you own.
        """
        if not resp:
            return await ctx.send(f"{ctx.author.mention} --> no content to edit with")
        v = await self.db.fetchrow("SELECT * FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, name)
        if v and await has_tag_edit_perm(self, ctx, name):
            await self.bot.db.execute("UPDATE tags VALUES SET response=? WHERE guild_id IS ? AND name=?", (resp, ctx.guild.id, name))
            await ctx.send(f"{ctx.author.mention} --> updated tag `{name}`")

    @tag.command(usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def claim(self, ctx, name: TagName):
        """
        allows you to claim a tag made by someone who is no longer in the server
        """
        data = await self.db.fetchrow("SELECT * FROM tags WHERE guild_id IS ? AND name IS ?", ctx.guild.id, name)
        if not data:
            return await ctx.send(f"{ctx.author.mention} --> that tag does not exist!")
        owner = ctx.guild.get_member(data[3])
        if owner is None:
            await self.db.execute("UPDATE tags SET owner = ? WHERE guild_id IS ? AND name IS ?", ctx.author.id, ctx.guild.id, name)
            await ctx.send(f"{ctx.author.mention} --> claimed tag {name}")
        else:
            await ctx.send(f"{ctx.author.mention} --> that tag already has an owner! ({owner})")
    
    @tag.command(usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def search(self, ctx, name: TagName):
        """
        preforms a search of your servers tags.
        """
        names = await self.db.fetchall("SELECT name FROM tags WHERE guild_id IS ?", ctx.guild.id)
        loop = asyncio.get_running_loop()
        def func():
            return difflib.get_close_matches(name, names, 15)
        names = await loop.run_in_executor(None, func)
        if not names:
            return await ctx.send("no matches found")
        pages = paginator.Pages(ctx, entries=names, per_page=5, embed_color=discord.Color.teal())
        await pages.paginate()

