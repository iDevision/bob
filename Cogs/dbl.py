from utils import commands

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
        v = await self.bot.session.post("https://discordextremelist.xyz/v1/bot/587482154938794028", headers=
        {"authorization": self.bot.settings['del_api_token']}, data={"guildCount": amo})
        if (await v.json())['error']:
            print((await v.json())['message'])

    def del_widget(self):
        return "https://discordextremelist.xyz/v1/bot/587482154938794028/widget"