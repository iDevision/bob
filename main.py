"""
Bob, a discord bot
Copyright (C) 2019  IAmTomahawkx

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
import calendar
import collections
import datetime
import json
import sys

import traceback
import logging
from logging import handlers
import uuid
import os

import aiohttp
import colorama
import discord
from discord.ext import tasks
import asyncpg

from utils import commands, errors, objects
from utils.context import Contexter

colorama.init(autoreset=True)


ids = {"BOB_ALPHA": 596223121527406603, "BOB": 587482154938794028}


logger = logging.getLogger("discord")
command_logger = logging.getLogger("commands")
warning_handler = handlers.TimedRotatingFileHandler(filename=os.path.join(os.path.dirname(__file__), 'logs', 'discord_warnings.log'), when="W0", encoding='utf-8', backupCount=10)
warning_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
warning_handler.setLevel(logging.WARNING)
logger.addHandler(warning_handler)
comm_handler = handlers.TimedRotatingFileHandler(filename=os.path.join(os.path.dirname(__file__), 'logs', 'commands.log'), when="W0", encoding='utf-8', backupCount=10)
comm_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
comm_handler.setLevel(logging.DEBUG)
command_logger.addHandler(comm_handler)


class _CaseInsensitiveDict(dict):
    def __contains__(self, k):
        return super().__contains__(k.lower())

    def __delitem__(self, k):
        return super().__delitem__(k.lower())

    def __getitem__(self, k):
        return super().__getitem__(k.lower())

    def get(self, k, default=None):
        return super().get(k.lower(), default)

    def pop(self, k, default=None):
        return super().pop(k.lower(), default)

    def __setitem__(self, k, v):
        super().__setitem__(k.lower(), v)


def parse_time(ps, return_times_instead=False):
    from utils import btime
    import calendar
    import parsedatetime
    cal = parsedatetime.Calendar()
    v = cal.nlp(ps)[0] # type: datetime.datetime
    if not return_times_instead:
        return calendar.timegm(v.replace(tzinfo=datetime.timezone.utc).timetuple())
    return btime.human_timedelta(v)


async def get_pre(bot, message):
    if not bot.setup:
        return bot.user.mention
    if message.guild is None:
        return ["!", "?", ""]
    try:
        l = [*bot.guild_prefixes[message.guild.id]]
    except:
        l = []
    if await bot.is_owner(message.author):
        l.append("$")
    return commands.when_mentioned_or(*l)(bot, message)


class Bot(commands.Bot):
    def __init__(self, prefix, help_command, description=None, **settings):
        self.settings = {}
        self.reload_settings()
        self.run_bot = self.settings['run_bot']
        from libraries import keys
        self._token = getattr(keys, self.run_bot+"_API_KEY")
        self.uhoh = getattr(keys, self.run_bot+"_UHOH")
        self.run_bot_display = self.settings['run_display_name']
        self.run_server = self.settings['server']
        self.pg = asyncio.get_event_loop().run_until_complete(asyncpg.create_pool(self.settings['postgresdsn'])) #type: asyncpg.pool.Pool
        #self.bridge = asyncio.get_event_loop().run_until_complete(asyncpg.create_pool(self.settings['postgresbridge'])) #type: asyncpg.pool.Pool
        self.counter = 0
        self.version = "unloaded"
        self.setup = False
        commands.Bot.__init__(self, prefix, help_command, description=description, **settings)
        self.__cogs = _CaseInsensitiveDict()
        from utils import db
        self.db = db.Database("general")
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.highlight_cache = {}
        self.custom_flags = ["mute"]
        self._custom_timers = []
        self.custom_event_loop.start()
        self.guild_prefixes = {}
        self.guild_module_states = {}
        self.guild_role_states = {}
        self.afks = {}
        self.timed_messages = {}
        self.uptime = 0
        self.logger, self.command_logger = logger, command_logger
        self.categories = {}
        self.bans = {}
        self.automod_states = {}
        self.logging_states = {}
        self.logging_ignore = []
        self.pings = collections.deque(maxlen=60)
        self.most_recent_change = self.changelog = None
        self.auths = {}
        self.streamers = {}


    def get_from_guildid(self, guildid):
        for a, b in self.twitch_cache.items():
            if b['guild_id'] == guildid:
                return a, b
        return None, None

    def get_from_userid(self, userid):
        for a, b in self.twitch_cache.items():
            if b['discord_id'] == userid:
                return a, b
        return None, None

    def get_from_twitchid(self, twitchid):
        for a, b in self.twitch_cache.items():
            if b['twitch_id'] == twitchid:
                return a,b
        return None, None

    async def get_context(self, message, *, cls=None):
        return await super().get_context(message, cls=cls or Contexter)

    def reload_settings(self):
        with open("settings.json") as f:
            self.settings = json.load(f)

    async def close(self):
        await bot.session.close()
        bot.custom_event_loop.cancel()
        lchan = self.get_channel(629167007807438858)
        await lchan.send(embed=commands.Embed(title="Disconnecting", color=commands.Color.dark_red()))
        await super().close()

    def create_task_and_count(self, coro):
        self.counter += 1

        async def do_stuff():
            await coro
            self.counter -= 1

        self.loop.create_task(do_stuff())

    @tasks.loop(seconds=1)
    async def custom_event_loop(self):
        now = calendar.timegm(datetime.datetime.utcnow().timetuple())
        for gid, flag, expiry, uid, payload in self._custom_timers:
            if expiry <= now:
                data = json.loads(payload)
                logger.debug("dispatching custom event: "+flag)
                self.dispatch(flag, data)
                self._custom_timers.remove((gid, flag, expiry, payload))
                await self.pg.execute("DELETE FROM timers WHERE guild_id = $1 AND uid IS $2", (gid, uid))

    async def schedule_timer(self, gid: int, flag: str, expiry: tuple, FromDict: dict=None, *args, **kwargs):
        payload = {}
        if FromDict is not None:
            payload.update(FromDict)
        if args:
            payload['args'] = [arg for arg in args]
        if kwargs:
            for key, val in kwargs.items():
                payload[key] = val
        payload['_expiry'] = list(expiry)
        payload['created_at'] = datetime.datetime.utcnow().timestamp()
        payload['guild_id'] = gid
        expiry = calendar.timegm(expiry)
        uid = str(uuid.uuid4())
        await self.pg.execute("INSERT INTO timers VALUES ($1,$2,$3,$4,$5)", gid, flag, expiry, uid, json.dumps(payload, ensure_ascii=False))
        # add it to a list so i dont have to make database calls every second in the custom event loop.
        self._custom_timers.append((gid, flag, expiry, uid, json.dumps(payload, ensure_ascii=False)))

    def get_category(self, name):
        return self.categories.get(name)

    def assign_category(self, name, cog):
        if name not in self.categories:
            self.categories[name] = commands.Category(name)
        self.categories[name].assign_cog(cog)

    def create_category(self, name, **kwargs):
        if name in self.categories:
            raise ValueError(f"the category {name} already exists")
        self.categories[name] = commands.Category(name, **kwargs)
        return self.categories[name]

    def remove_category(self, name):
        if name not in self.categories:
            raise ValueError(f"the category {name} does not exist")
        return self.categories.pop(name)

    async def on_message(self, message):
        if message.author.bot or not bot.is_ready() or not bot.setup:
            return

        curr = self.get_cog("Currency")

        if curr is not None:
            curr.activity.update_rate_limit(message)

        if message.guild.id not in self.logging_states:
            rec = await self.pg.fetchrow("SELECT * FROM modlogs WHERE guild_id = $1;", message.guild.id)
            if not rec:
                self.logging_states[message.guild.id] = None

            else:
                self.logging_states[message.guild.id] = objects.LoggingFlags(self.pg, rec)

        ctx = await self.get_context(message)

        if ctx.command is None and self.user in message.mentions:
            await self.get_cog("Bull").run_ping(ctx)

        await self.invoke(ctx)

    async def on_command(self, ctx):
        command_logger.info(
            f"Running command `{ctx.command.qualified_name}`. invoked by `{ctx.author}`. content: {ctx.message.content}")

    async def on_error(self, event, *args, **kwargs):
        if isinstance(sys.exc_info()[0], commands.CommandError):
            return  # handled by on_command_error
        traceback.print_exc()
        try:
            e = discord.Embed(name="Error occurred")
            e.description = traceback.format_stack(sys.exc_info()[2])
            e.colour = discord.Color.red()
            await bot.get_channel(bot.uhoh).send(f"<@547861735391100931>", embed=e)
        except Exception:
            pass

bot = Bot(get_pre, help_command=None, case_insensitive=True, owner_ids=[547861735391100931, 396177665742077956])

@bot.check
async def check_bans(ctx):
    if ctx.author.id in ctx.bot.bans:
        raise errors.BannedUser(ctx.author)
    return True

bot.load_extension("jishaku")
for i in bot.settings['initial_cogs']:
    bot.load_extension("Cogs."+i)

if __name__ == "__main__":
    print("starting...")
    print(colorama.Fore.LIGHTMAGENTA_EX + """===================================
    ____    ____     ____
   / __ )  / __ \   / __ )
  / __  | / / / /  / __  |
 / /_/ / / /_/ /  / /_/ /
/_____/  \____/  /_____/
===================================""")
    try:
        bot.run(bot._token)
    except:
        print("")
        traceback.print_exc()
    finally:
        print("shutdown complete")
