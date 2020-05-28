from utils import commands
import random
import json

def setup(bot):
    bot.add_cog(Bull(bot))

class Bull(commands.Cog):
    hidden = True
    def __init__(self, bot):
        self.bot = bot
        self.ban_messages = [
            "$u, you must serve your sentence. $m",
            "$u, did you really think you would escape consequences? $m",
            "$u, the thou shalt not pass anymore! $m",
            "nuh uh, I don't think so $u. $m"
        ]
        with open("data/bullshit.json") as f:
            self.mention_messages = json.load(f)

    @commands.command()
    @commands.is_owner()
    async def add_mention(self, ctx, *, entry):
        entry += "\n$m"
        self.mention_messages.append(entry)

        with open("./data/bullshit.json", "w") as f:
            json.dump(self.mention_messages, f)
        await ctx.send("Done")

    async def run_ping(self, ctx):
        await ctx.send(random.choice(self.mention_messages).replace("$m", f""))

    async def run_ban(self, ctx):
        await ctx.send(random.choice(self.ban_messages).replace("$u", str(ctx.author)).replace("$m", "\n\n*You have been banned from this bot. If you believe this is a mistake, please contact the support server.*"))
