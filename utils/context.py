import asyncio

import discord
from discord.ext import commands
from discord.ext.commands.context import Context as _context

from . import paginator as _paginator


def boolize(string):
    string = string.lower()
    if string in ["true", "yes", "on", "enabled", "y", "t", "1"]:
        return True
    elif string in ["false", "no", "off", "disabled", "n", "f", "0"]:
        return False
    else:
        raise commands.UserInputError(f"{string} is not a recognized boolean option")

class Contexter(_context):
    async def paginate_fields(self, fields, **kwargs):
        pages = _paginator.FieldPages(self, entries=fields, **kwargs)
        await pages.paginate()

    async def paginate(self, fields, **kwargs):
        pages = _paginator.Pages(self, entries=fields, **kwargs)
        await pages.paginate()

    async def ask(self, question, return_bool=True, timeout=60.0):
        await self.send(question)
        def predicate(msg):
            return msg.channel == self.channel and msg.author == self.author
        try:
            m = await self.bot.wait_for("message", timeout=timeout, check=predicate)
        except asyncio.TimeoutError:
            raise commands.CommandError("timeout reached. aborting.")
        if not return_bool:
            return m.content
        return boolize(m.content)

    def embed(self, **kwargs):
        return discord.Embed(color=discord.Color.teal(), **kwargs)

    def embed_invis(self, **kwargs):
        return discord.Embed(color=0x36393E, **kwargs)