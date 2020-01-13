from utils import commands
import aiohttp
import io

def setup(bot):
    bot.add_cog(dbl(bot))

class dbl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild, loader=False):
        if loader:
            return
        if self.bot.settings['run_bot'] != "BOB":
            return
        await self.dummycount(len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_leave(self, guild):
        await self.on_guild_join(guild)

    async def dummycount(self, amo):
        await self.bot.session.post("https://api.discordextremelist.xyz/v1/bot/587482154938794028", headers=
        {"authorization": self.bot.settings['del_api_token']}, data={"guildCount": amo})
        await self.bot.session.post("https://top.gg/api/bots/587482154938794028/stats", data={"server_count": amo},
                                        headers={"Authorization": self.bot.settings['dbl_api_token']})

    async def del_widget(self):
        v = await self.bot.session.get("https://api.discordextremelist.xyz/v1/bot/587482154938794028/widget") #type:aiohttp.ClientResponse
        a = io.BytesIO(await v.read())
        a.seek(0)
        return commands.File(a, filename="del_widget.png")

    async def dbl_widget(self):
        v = await self.bot.session.get(
            "https://top.gg/api/widget/587482154938794028.png")  # type:aiohttp.ClientResponse
        a = io.BytesIO(await v.read())
        a.seek(0)
        return commands.File(a, filename="dbl_widget.png")
        return "https://top.gg/api/widget/587482154938794028.png"

    @commands.command()
    @commands.is_owner()
    async def widgets(self, ctx):
        delly = await self.del_widget()
        dbl = await self.dbl_widget()
        await ctx.send(files=[delly, dbl])
