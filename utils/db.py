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
    "events": "CREATE TABLE IF NOT EXISTS events (guild_id integer, member_join integer, member_join_msg text, member_leave integer, member_leave_msg text);",
    "rtfm": "CREATE TABLE IF NOT EXISTS default_rtfm (guild_id integer, name text); CREATE TABLE IF NOT EXISTS pages (quick text, long text, url text); CREATE TABLE IF NOT EXISTS waiting (user integer, quick text, long text, url text);--",
    "reminders": """CREATE TABLE IF NOT EXISTS reminders (guild_id integer, channel_id integer, message text, remind_time real, msg_link text, user_id integer, uuid text);--""",
    "automod": """CREATE TABLE IF NOT EXISTS automod_ignore (guild_id integer, type text, ignore_id integer);
    CREATE TABLE IF NOT EXISTS automod_config (guild_id integer, enabled integer, banned_words_punishment integer, message_spam_messages integer, message_spam_delay integer, message_spam_punishment integer, mass_mentions_max integer, mass_mentions_punishment integer, all_caps_punishment integer, all_caps_percent integer, invites_punishment integer, links_punishment integer);
    CREATE TABLE IF NOT EXISTS automod_banned_words (guild_id integer, word text);--""",
    "customcommands": """CREATE TABLE IF NOT EXISTS custom_commands (guild_id integer, trigger text, response text, uses integer);--""",
    "configs": """CREATE TABLE IF NOT EXISTS guild_configs (guild_id integer, announce_streams integer, announce_channel integer, announce_channel_streams integer, mod_logs_channel integer, warns_before_silence integer, prefix text, warn_mute_length integer, automute_safe_role integer, automod_channel integer, premium_code text, premium_authorized integer);--""",
    "fun": "",
    "logs": """CREATE TABLE IF NOT EXISTS modlogs (guild_id integer, member_join integer, member_leave integer, member_nickname_change integer, member_isbanned integer, member_isunbanned integer, member_iskicked integer, message_delete integer, message_edit integer, message_bulk_delete integer, role_create integer, role_edit integer, role_delete integer, channel_create integer, channel_edit integer, channel_delete integer, emojis_update integer, channel integer);""",
    "currency": """CREATE TABLE IF NOT EXISTS currency (guild_id integer, user_id integer, points integer);--""",
    "community": """CREATE TABLE IF NOT EXISTS poll_nodes (guild_id integer, poll_id text, emoji text, description text);
    CREATE TABLE IF NOT EXISTS polls (guild_id integer, poll_id text, end integer, endtext text, title text, description text, channel integer, msgid integer);
    CREATE TABLE IF NOT EXISTS giveaway_settings (guild_id integer, required_points integer, enabled integer, entry_limit integer);
    CREATE TABLE IF NOT EXISTS giveaway_entries (guild_id integer, user_id integer, times integer);--""",
    "quotes": """CREATE TABLE IF NOT EXISTS quotes (guild_id integer, manager integer, content text, id integer);--""",
    "tags": """CREATE TABLE IF NOT EXISTS tags (guild_id integer, name text, response text, owner integer, uses integer);--""",
    "moderation": """CREATE TABLE IF NOT EXISTS warnings (guild_id integer, user_id integer, moderator integer, reason text, caseno text);
    CREATE TABLE IF NOT EXISTS moddata (guild_id integer, user_id integer, moderator_id integer, note text, time integer);""",
    "general": """
    CREATE TABLE IF NOT EXISTS module_states (guild_id integer, moderator integer, quotes integer, giveaway integer, automod integer, modlogs integer, community integer, fun integer, music integer, autoresponder integer, events integer, currency integer, modmail integer, basics integer, commands integer, tags integer, qotd integer, twitch_interg integer, highlight integer);
    CREATE TABLE IF NOT EXISTS timers (guild_id integer, flag text, expiry float, uid text, payload text);
    CREATE TABLE IF NOT EXISTS role_auto_assign (guild_id integer, role_id integer);
    CREATE TABLE IF NOT EXISTS roles (guild_id integer, editor integer, muted integer, moderator integer, manager integer, streamer integer);
    CREATE TABLE IF NOT EXISTS guild_members (guild_id integer, user_id integer, streaming_msg_id integer, warns_since_last_mute integer);
    CREATE TABLE IF NOT EXISTS reminders (guild_id integer, channel_id integer, message text, remind_time real, msg_link text, user_id integer, uuid text);
    CREATE TABLE IF NOT EXISTS afks (guild_id integer, user_id integer, reason text);
    CREATE TABLE IF NOT EXISTS counters (guild_id integer, count_to real, expiry_message text);
    CREATE TABLE IF NOT EXISTS role_persists (guild_id integer, role_id integer);
    CREATE TABLE IF NOT EXISTS reaction_roles (guild_id integer, role_id integer, emoji_id text, message_id integer, channel_id integer, mode integer);
    CREATE TABLE IF NOT EXISTS highlights (guild_id integer, user_id integer, word text);
    CREATE TABLE IF NOT EXISTS hl_blocks (guild_id integer, user_id integer, rcid integer, rc integer);
    CREATE TABLE IF NOT EXISTS bans (user_id, reason);
    CREATE TABLE IF NOT EXISTS mutes (guild_id, user_id, reason text);--""",  # that last one is really just a lazyloader
    "global": """CREATE TABLE IF NOT EXISTS PREMIUM_GUILD_KEYS (guild_id integer, key text, expiry text);
        CREATE TABLE IF NOT EXISTS USERS (user_id integer, total_messages integer, warns text, quote text);
        CREATE TABLE IF NOT EXISTS IDEAS (user_id integer, type text, msg text, msgid integer);
        CREATE TABLE IF NOT EXISTS IDEAS_banned (user_id);--""",
    "qotd": "CREATE TABLE IF NOT EXISTS qotd (guild_id integer, channel_id integer);"
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