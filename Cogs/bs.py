from utils import commands
import random

def setup(bot):
    bot.add_cog(Bull(bot))

class Bull(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ban_messages = [
            "$u, you must serve your sentence. $m",
            "$u, did you really think you would escape consequences? $m",
            "$u, the thou shalt not pass anymore! $m"
        ]
        self.mention_messages = [
            "Yes?\n$m",
            "\*Lurks intently\*\n$m",
            "Can I help you?\n$m",
            "\U0001f693\n$m",
            "<:cctv:587262240688701440>\n$m",
            "<:typing:585888124761276416>\n$m",
            "<:ping:655484718225293368>\n$m",
            "<a:whomstve_ping_me:668320147366346774>\n$m",
            "how make i say computer \"hi\"?\n$m",
            "Woah, we're halfway there\nWoah-oh, livin' on a prayer\nTake my hand, we'll make it I swear\nWoah-oh, livin' on a prayer, livin' on a prayer\n$m",
            "\*sings 'Through the fire and the flames'\*\n$m",
            "APPLICATION DATA AFTER CLOSE NOTIFY\n$m",
            "Noobmaster, hey it’s Thor again. You know, the god of thunder? Listen buddy, if you don’t log off this game "
            "immediately I will fly over to your house, and come down to that basement you’re hiding in and rip off your "
            "arms and shove them up your butt! Oh, that’s right, yea just go cry to your father you little weasel.\n$m"
        ]

    async def run_ping(self, ctx):
        await ctx.send(random.choice(self.mention_messages).replace("$m", f"\n*Your server's prefix is `{ctx.bot.guild_prefixes[ctx.guild.id]}`*"))

    async def run_ban(self, ctx):
        await ctx.send(random.choice(self.ban_messages).replace("$u", str(ctx.author)).replace("$m", "\n\n*You have been banned from this bot. If you believe this is a mistake, please contact the support server.*"))