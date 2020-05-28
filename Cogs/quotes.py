import random

from utils import commands
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

    def cog_check(self, ctx):
        raise commands.CheckFailure("Quotes are disabled.")

    @commands.group(invoke_without_command=True, aliases=["quotes"])
    @commands.cooler()
    async def quote(self, ctx, q: int = None):
        """
        get a quote from your server! anyone can use this command! **QUOTES ARE CURRENTLY DISABLED UNTIL TWITCH LAUNCH**
        ... due to internal changes, quotes will be unusable by anyone other than twitch beta testers until twitch goes public. sorry :(
        optionally, you can specify a quote number.
        """
        sock = self.bot.get_cog("sock")
        if not sock:
            return await ctx.send("this function is not available right now")
        v = self.bot.get_from_guildid(ctx.guild.id)
        if v[0] is None:
            return await ctx.send("sorry, this server does not have a twitch link set up to put quotes into.")
        quotes = await sock.reply({"_t": "GET_QUOTE", "all": True, "user_token": v[0]})
        quotes = quotes.get("quotes", {})
        if not quotes:
            return await ctx.send("no quotes available!")
        if q is not None:
            for t, qn in quotes.items():
                if qn == q:
                    return await ctx.send(f"quote {qn}: {t}")
        pres = []
        for i in quotes.items():
            if not isinstance(i, tuple):
                continue
            pres.append(f"quote #{i[0]}: {i[1]}")
        await ctx.send(random.choice(pres))

    @quote.command("list")
    @commands.cooler()
    async def listquotes(self, ctx):
        """
        view a list of your servers quotes
        """
        sock = self.bot.get_cog("sock")
        if not sock:
            return await ctx.send("this function is not available right now")
        v = self.bot.get_from_guildid(ctx.guild.id)
        if v[0] is None:
            return await ctx.send("sorry, this server does not have a twitch link set up to put quotes into.")
        quotes = await sock.reply({"_t": "GET_QUOTE", "all":True, "user_token": v[0]})
        quotes = quotes.get("quotes", {})
        if not quotes:
            return await ctx.send("no quotes available!")
        pres = []
        for i in quotes.items():
            pres.append(f"{i[0]}. {i[1]}")
        await ctx.paginate(pres, nocount=True)

    @quote.command("add")
    @check_manager()
    @commands.cooler()
    async def addquote(self, ctx, *, msg: commands.clean_content):
        """
        add a "sacred texts" to your server's quote list!
        requires the `Community Manager` role or Higher
        """
        sock = self.bot.get_cog("sock")
        if not sock:
            return await ctx.send("this function is not available right now")
        v = self.bot.get_from_guildid(ctx.guild.id)
        if v[0] is None:
            return await ctx.send("sorry, this server does not have a twitch link set up to put quotes into.")

        resp = await sock.reply({"_t": "ADD_QUOTE", "user_token": v[0], "text": msg})
        print(resp)
        if resp['code'] != 200:
            return await ctx.send("failed to add the quote!")
        await ctx.send(f"{ctx.author.mention} --> added quote {resp.get('num')}")


    @quote.command("remove", aliases=["rm", "delete"], hidden=True)
    @check_manager()
    @commands.cooler()
    async def remquote(self, ctx, rem: int):
        """
        delete part of the "sacred texts" from your server.
        requires the `Community Manager` role or higher
        """
        return
        data = await self.db.fetchall("SELECT * FROM quotes WHERE guild_id IS ?", ctx.guild.id)
        l = max(x[3] for x in data)
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
        sock = self.bot.get_cog("sock")
        if not sock:
            return await ctx.send("this function is not available right now")
        v = self.bot.get_from_guildid(ctx.guild.id)
        if v[0] is None:
            return await ctx.send("sorry, this server does not have a twitch link set up to put quotes into.")

        resp = await sock.reply({"_t": "ALTER_QUOTE", "user_token": v[0], "id": num, "text": msg})
        if resp['code'] != 200:
            return await ctx.send("couldnt find that quote. does it exist?")
        await ctx.send(f"updated quote {num}")
