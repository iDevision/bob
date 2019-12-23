import asyncio
import json
import os

import aiosqlite3

with open("settings.json") as f:
    data = json.load(f)
    run = data['run_bot']
databases_pth = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "databases")

def getfile(name):
    return os.path.join(databases_pth, run+"_"+name+".db")

modules = {
    "rtfm": getfile("api"),
    "automod": getfile("automod"),
    "reminders": getfile("reminders"),
    "customcommands": getfile("customcommands"),
    "configs": getfile("guild_configs"),
    "fun": getfile("fun"),
    "moderation": getfile("moderation"),
    "logs": getfile("logs"),
    "currency": getfile("currency"),
    "community": getfile("community"),
    "quotes": getfile("quotes"),
    "tags": getfile("tags"),
    "general": getfile("general"),
    "global": getfile("global"),
    "events": getfile("events"),
    "qotd": getfile("qotd")
}

module_executors = {
    # removed for anti-others-running-my-bot reason
}

class Database:
    def __init__(self, module):
        self.module = module
        self.db_path = modules[module]
        self.connection = None
        self.lock = asyncio.Lock()

    async def close(self):
        if self.connection is not None:
            await self.connection.close()

    async def setup(self):
        self.connection = await aiosqlite3.connect(self.db_path)
        try:
            await self.connection.executescript(module_executors[self.module])
        except aiosqlite3.OperationalError:
            pass

    async def cursor(self):
        # not really sure why this is async, but ok
        if self.connection is None:
            await self.setup()
        return await self.connection.cursor()  # like, seriously?

    async def execute(self, stmt: str, *values):
        async with self.lock:
            if self.connection is None:
                await self.setup()

            if len(values) == 1 and isinstance(values[0], tuple):
                values = values[0]
            try:
                ret = await self.connection.execute(stmt, tuple(values))
            except aiosqlite3.OperationalError:
                raise
            except SystemError:
                try:
                    await self.connection.commit()
                except (aiosqlite3.OperationalError, SystemError):
                    pass # this keeps passing the "not an error" error.
                else:
                    raise
            else:
                try:
                    await self.connection.commit()
                except aiosqlite3.OperationalError:
                    pass # this keeps passing the "not an error" error.
                return ret

    async def update_user_data(self, bot, user, guild, *, points=0, total_msg=0, set_total=False):
        existing_p, existing_t, _ = await self.fetch_user_data(bot, user, guild)
        if points != 0 and existing_p is not None:
            await bot.get_cog("points").db.execute("UPDATE guild_members SET points = ? WHERE guild_id IS ? AND user_id IS ?", (points+existing_p if not set_total else points, guild.id, user.id))
        if total_msg != 0 and existing_t is not None:
            if not set_total:
                existing_t += total_msg
            else:
                existing_t = total_msg
            await bot.db.execute(f"UPDATE guild_members SET total_messages = ? WHERE guild_id IS ? AND user_id IS ?",
                               (existing_t, guild.id, user.id))

    async def fetch_user_data(self, bot, user, guild):
        points = await bot.get_cog("points").db.fetch("SELECT points FROM guild_members WHERE guild_id IS ? AND user_id IS ?",
                           guild.id, user.id)
        if points is None:
            await bot.get_cog("points").db.execute("INSERT INTO guild_members VALUES (?,?,0,0)",
                           guild.id, user.id)
            points = 0

        sml = await bot.db.fetchrow("SELECT total_messages, total_warnings FROM guild_members WHERE guild_id IS ? AND user_id IS ?",
                           guild.id, user.id)
        if sml is None:
            await bot.db.execute("INSERT INTO guild_members VALUES (?,?,0,0,0,0)", guild.id, user.id)
            msg, warns = 0,0
        else:
            msg, warns = sml
        return points, msg, warns

    async def fetch(self, stmt: str, *values, default=None):
        """
        :param stmt: the SQL statement
        :param values: the values to be sanitized
        :param default: the default to return if no value was found, or if an error occurred
        :return: the first value in the fetched row
        """
        async with self.lock:
            if self.connection is None:
                await self.setup()
            if len(values) == 1 and isinstance(values[0], tuple):
                values = values[0]
            try:
                return (await (await self.connection.execute(stmt, tuple(values))).fetchone())[0] or default
            except Exception:
                return default

    async def fetchrow(self, stmt: str, *values):
        """
        :param stmt: the SQL statement
        :param values: the values to be sanitized
        :return: the fetched row
        """
        async with self.lock:
            if self.connection is None:
                await self.setup()
            if len(values) == 1 and isinstance(values[0], tuple):
                values = values[0]
            try:
                return await (await self.connection.execute(stmt, tuple(values))).fetchone()
            except Exception:
                return None
    
    async def fetchall(self, stmt: str, *values):
        async with self.lock:
            if self.connection is None:
                await self.setup()
            if len(values) == 1 and isinstance(values[0], tuple):
                values = values[0]
            try:
                return await (await self.connection.execute(stmt, tuple(values))).fetchall()
            except Exception:
                return None

    async def commit(self):
        if self.connection is None:
            await self.setup()
        try:
            await self.connection.commit()
        except: pass

    async def executemany(self, stmt: str, values: list):
        async with self.lock:
            if self.connection is None:
                await self.setup()
            if self.connection._conn is None:
                await self.connection.connect()
            try:
                await self.connection.executemany(stmt, values)
            except aiosqlite3.OperationalError:
                await self.connection.rollback()
                raise
            else:
                await self.connection.commit()

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.connection.__exit__(exc_type, exc_val, exc_tb)

def format_asyncpg(string: str):
    amo = 0
    out = ""
    for char in string:
        if char == "?":
            out += "$"+str(amo)
            continue
        out += char
    return out
