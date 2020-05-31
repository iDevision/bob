import asyncio
import datetime
import difflib
import typing

import discord

from utils import db, paginator, commands
from utils.checks import basic_check, check_module


def setup(bot):
    bot.add_cog(_tags(bot))


class TagName(commands.clean_content):
    def __init__(self, *, lower=True):
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


async def has_tag_edit_perm(ctx, tag, owner_id):
    try:
        if await basic_check(ctx, "moderator", "editor"):
            return True
    except:
        pass

    if ctx.author.id == owner_id:
        return True

    return False


class _tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @commands.guild_only()
    @check_module("tags")
    async def tags(self, ctx, user: typing.Union[commands.Member, int]=None):
        await self._list(ctx, user)

    @tags.command("list")
    @commands.guild_only()
    @check_module('tags')
    async def _list(self, ctx, user: typing.Union[commands.Member, int]=None):
        if not user:
            user = ctx.author
        if isinstance(user, int):
         user = commands.Object(id=user)

        tags = await self.bot.pg.fetch("SELECT name FROM tags WHERE guild_id = $1 AND owner = $2", ctx.guild.id, user.id)
        if not tags:
            return await ctx.send(f"{user} has no tags!")

        v = [t['name'] for t in tags]
        await ctx.paginate(v)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @check_module('tags')
    async def tag(self, ctx: commands.Context, *, searchtag: TagName = None):
        """
        responds with a tag, if it exists.
        tags can be created by anyone, and used by anyone. they're like custom commands, but public.
        tags can be created with the `tag create` command.
        """
        if searchtag is None:
            return await ctx.send_help(ctx.command)

        match = await self.bot.pg.fetchval("UPDATE tags SET uses=uses+1 WHERE guild_id = $1 AND name = $2 RETURNING response",ctx.guild.id, searchtag)

        if match:
            await ctx.send(match)

        else:
            names = await self.bot.pg.fetch("SELECT name FROM tags WHERE guild_id = $1", ctx.guild.id)
            names = [x['name'] for x in names]

            def func():
                return difflib.get_close_matches(searchtag, names, 5)
            names = await self.bot.loop.run_in_executor(None, func)
            if names:
                e = discord.Embed(color=discord.Colour.from_rgb(54, 57, 62))
                e.title = "tag not found. maybe you meant one of these?"
                e.description ="``"+ "``\n``".join(names) + "``"
                return await ctx.send(embed=e)

            await ctx.send("that tag does not exist!")

    @tag.command(aliases=["add", "make"], usage="<name> [response]")
    @commands.guild_only()
    @check_module('tags')
    async def create(self, ctx: commands.Context, name: TagName, *, resp: commands.clean_content=None):
        if not resp:
            resp = await ctx.ask(f"creating tag `{name}`. what should the content be? (type {ctx.prefix}cancel to cancel)", return_bool=False, timeout=60)
            if resp.startswith(ctx.prefix + "cancel"):
                return await ctx.send("cancelling.")

            resp = await commands.clean_content().convert(ctx, resp)

        try:
            await self.bot.pg.execute("INSERT INTO tags VALUES ($1,$2,$3,$4,0)", ctx.guild.id, name, resp, ctx.author.id)
        except:
            return await ctx.send("that tag already exists.")

        await ctx.send(f"created tag {name}")


    @tag.command(aliases=["delete", "rm", "del"], usage="<name>")
    @commands.guild_only()
    @check_module('tags')
    async def remove(self, ctx, name: TagName):
        v = await self.bot.pg.fetchrow("SELECT * FROM tags WHERE guild_id = $1 AND name = $2", ctx.guild.id, name)
        if v and await has_tag_edit_perm(ctx, name, v['owner']):
            await self.bot.pg.execute("DELETE FROM tags WHERE guild_id = $1 AND name = $2", ctx.guild.id, name)
            await ctx.send(f"successfully removed tag `{commands.utils.escape_markdown(name)}`")

        elif v and not await has_tag_edit_perm(ctx, name, v['owner']):
            await ctx.send("that tag isn't yours to delete")

        else:
            await ctx.send("that tag does not exist")


    @tag.command(aliases=["?"], usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def info(self, ctx, name: TagName):
        """
        shows info about a tag.
        this includes things like the owner and how many times the tag has been used.
        """
        data = await self.bot.pg.fetchrow("SELECT * FROM tags WHERE guild_id = $1 AND name = $2", ctx.guild.id, name)
        if not data:
            return await ctx.send("That tag does not exist")

        e = ctx.embed_invis()
        owner = ctx.guild.get_member(data['owner']) or data['owner']
        e.add_field(name="Owner", value=str(owner))
        e.add_field(name="Uses", value=data[4])
        if not isinstance(owner, int):
            e.set_author(name=str(owner), icon_url=owner.avatar_url)
        else:
            e.set_author(name=str(owner))

        e.timestamp = datetime.datetime.utcnow()
        await ctx.send(embed=e)

    @tag.command(usage="<tag name> <content>")
    @commands.guild_only()
    @check_module('tags')
    async def edit(self, ctx, name: TagName, *, resp: commands.clean_content):
        """
        allows you to edit a tag you own.
        """

        v = await self.bot.pg.fetchrow("SELECT * FROM tags WHERE guild_id = $1 AND name = $2", ctx.guild.id, name)

        if v and await has_tag_edit_perm(ctx, name, v['owner']):
            await self.bot.pg.execute("UPDATE tags SET response = $1 WHERE guild_id = $2 AND name=$3", resp, ctx.guild.id, name)
            await ctx.send(f"Updated tag `{name}`")
        elif v:
            await ctx.send("that tag is not yours to edit")

    @tag.command(usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def claim(self, ctx, name: TagName):
        """
        allows you to claim a tag made by someone who is no longer in the server
        """
        data = await self.bot.pg.fetchrow("SELECT * FROM tags WHERE guild_id = $1 AND name = $2", ctx.guild.id, name)
        if not data:
            return await ctx.send("that tag does not exist")

        owner = ctx.guild.get_member(data['owner'])
        if owner is None:
            await self.bot.pg.execute("UPDATE tags SET owner = $1 WHERE guild_id = $2 AND name = $3", ctx.author.id, ctx.guild.id, name)
            await ctx.send(f"claimed tag `{name}`")
        else:
            await ctx.send(f"that tag already has an owner ({owner})")
    
    @tag.command(usage="<tag name>")
    @commands.guild_only()
    @check_module('tags')
    async def search(self, ctx, name: TagName):
        """
        preforms a search of your servers tags.
        """
        names = await self.bot.pg.fetch("SELECT name FROM tags WHERE guild_id = $1", ctx.guild.id)
        names = [tag['name'] for tag in names]
        def func():
            return difflib.get_close_matches(name, names, 15)

        names = await self.bot.loop.run_in_executor(None, func)
        if not names:
            return await ctx.send("no matches found")

        await ctx.paginate(names)

