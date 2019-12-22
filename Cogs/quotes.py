import random

from utils import db, commands
from utils.checks import *


# TODO: add channel where quotes go when created
# TODO: add !quotethat command to quote above message?
# TODO: add image support?

def setup(bot):
    bot.add_cog(__quotes(bot))

class __quotes(commands.Cog):
    category="quotes"
    walk_on_help = True
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("quotes")

    @commands.group(invoke_without_command=True, aliases=["quotes"])
    @commands.cooler()
    async def quote(self, ctx, q: int = None):
        """
        get a quote from your server! anyone can use this command!
        optionally, you can specify a quote number.
        """
        db = await self.db.fetchall("SELECT content, id FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        if q is not None:
            if q > len(db) or q < 0:
                return await ctx.send(f"{ctx.author.mention} --> that quote doesnt exist!")
        else:
            if not len(db):
                return await ctx.send(f"{ctx.author.mention} --> no quotes exist!")
            q = random.randint(1, len(db))

        for c, id in db:
            if id is q:
                await ctx.send(f"quote #{q}: {c}")
                break

    @quote.command("list")
    @commands.cooler()
    async def listquotes(self, ctx):
        """
        view a list of your servers quotes
        """
        quotes = await self.db.fetchall("SELECT content, id FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        pres = []
        for i in quotes:
            if not isinstance(i, tuple):
                print(i)
                continue
            pres.append(f"{i[1]}. {i[0]}")
        await ctx.paginate(pres, nocount=True)

    @quote.command("add")
    @check_manager()
    @commands.cooler()
    async def addquote(self, ctx, *, msg: commands.clean_content):
        """
        add a "sacred texts" to your server's quote list!
        requires the `Community Manager` role or Higher
        """
        data = await self.db.fetchall("SELECT * FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        l = max(x[3] for x in data)
        await self.db.execute("INSERT INTO quotes VALUES (?,?,?,?)",
                                  (ctx.guild.id, ctx.author.id, msg, l+1))
        await ctx.send(f"{ctx.author.mention} --> added quote {l+1}")


    @quote.command("remove", aliases=["rm", "delete"])
    @check_manager()
    @commands.cooler()
    async def remquote(self, ctx, rem: int):
        """
        delete part of the "sacred texts" from your server.
        requires the `Community Manager` role or higher
        """
        data = await self.db.fetchall("SELECT * FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        l = max(x[3] for x in data)
        print(l)
        if rem > l or rem < 0:
            return await ctx.send(f"{ctx.author.mention} --> that quote doesnt exist!")
        await self.db.execute("DELETE FROM quotes WHERE guild_id IS ? AND id IS ?", ctx.guild.id, rem)
        await ctx.send(f"{ctx.author.mention} --> removed quote #{rem}")

    @quote.command("edit")
    @check_manager()
    @commands.cooler()
    async def editquote(self, ctx, num: int, *, msg: commands.clean_content):
        """
        edit the "sacred texts".
        requires the `Community Manager` role or higher.
        """
        data = await self.db.fetchall("SELECT * FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        l = max(x[3] for x in data)
        if num > l or num < 0:
            return await ctx.send(f"{ctx.author.mention} --> that quote doesnt exist!")
        await self.db.execute("UPDATE quotes SET content=? WHERE guild_id IS ? AND id IS ?", msg, ctx.guild.id, num)
        await ctx.send(f"{ctx.author.mention} --> edited quote #{num}")
