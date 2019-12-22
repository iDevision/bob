import asyncio
import websockets
import collections
import json

from utils import commands


def setup(bot):
    bot.add_cog(sock(bot))

class sock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if hasattr(bot, "ipc"):
            self.ws = bot.ipc
        else:
            bot.loop.create_task()

    async def new_connection(self):
        self.bot.ipc = self.ws = await websockets.connect("127.0.0.1:2223")


    def get_links(self, twitchid=None, discordid=None, guild_id=None, user_token=None):
        for t in self.bot.tokens:
            if twitchid is not None:
                if t.twitch_id == twitchid:
                    return t
            elif discordid is not None:
                if t.discord_id == discordid:
                    return t
            elif guild_id is not None:
                if t.guild_id == guild_id:
                    return t
            elif user_token is not None:
                if t.user_token == user_token:
                    return t
            else:
                raise ValueError("need at least one value")

    async def pull_accounts(self, *twitch_ids):
        if not twitch_ids:
            # pull all
            payload = {"_t": "SYNC_ACCOUNTS", "all": True, "twitch_ids": []}
            data = await self.reply(payload)
        else:
            payload = {"_t": "SYNC_ACCOUNTS", "all": False, "twitch_ids": [*twitch_ids]}
            data = await self.reply(payload)
        if data['code'] != 200:
            return  # the request failed
        tups = []
        for i in data.get('response'):  # should be a list of dicts
            v = collections.namedtuple("user connections", ['user_token', 'twitch_id', 'discord_id', 'guild_id'])
            v.user_token = i['user_token']
            v.guild_id = i['guild_id']
            v.discord_id = i['discord_id']
            v.twitch_id = i['twitch_id']
            tups.append(v)
        for num, i in enumerate(self.bot.tokens):
            for t in tups:
                if i.user_token == t.user_token:
                    self.bot.tokens[num] = t
                    tups.remove(t)
                    break
        for i in tups:
            self.bot.tokens.append(i)
