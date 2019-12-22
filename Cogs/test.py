from utils import commands

def setup(bot):
    bot.add_cog(Test(bot))

class Test(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

#    async def cog_check(self, ctx):
#        return ctx.author.id == 655237635102736424

    @commands.command()
    async def sockettest(self, ctx, data):
        sock = self.bot.get_cog("sock")
        await ctx.send(str(await sock.put_reply({"_t": data})))

    @commands.command()
    async def socketsend(self, ctx, d):
        sock = self.bot.get_cog("sock")
        await sock.write({"_t":d})