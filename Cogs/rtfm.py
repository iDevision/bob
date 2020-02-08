# most of the actual reading-of-docs stuff here is borrowed from R. Danny
import io
import os
import re
import zlib
import datetime

import discord
from discord.ext import commands as _root_commands, tasks as _root_tasks

from utils import checks, errors, paginator
from utils import db, commands
import inspect
import aiohttp


def setup(bot):
    bot.add_cog(_rtfm(bot))

def finder(text, collection, labels=True, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        if not labels and to_search.startswith("label:"):
            continue
        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    def sort_key(tup):
        if key:
            return tup[0], tup[1], key(tup[2])
        return tup

    if lazy:
        return (z for _, _, z in sorted(suggestions, key=sort_key))
    else:
        return [z for _, _, z in sorted(suggestions, key=sort_key)]


class SphinxObjectFileReader:
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode('utf-8')

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b''
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode('utf-8')
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')

class _rtfm(commands.Cog):
    category="misc"
    def __init__(self, bot):
        self.bot = bot
        self.db = db.Database("rtfm")
        self.defaults = {}
        self.pages = {}
        self.usage = {}
        self._rtfm_cache = None
        self.offload_unused_cache.start()

    def cog_unload(self):
        self.offload_unused_cache.cancel()

    @_root_tasks.loop(minutes=1)
    async def offload_unused_cache(self):
        now = datetime.datetime.utcnow()
        for key, i in self.usage.items():
            if (now-i).minute >= 20 and key in self._rtfm_cache:
                del self._rtfm_cache[key]


    def parse_object_inv(self, stream, url):
        # key: URL
        result = {}

        # first line is version info
        inv_version = stream.readline().rstrip()

        if inv_version != '# Sphinx inventory version 2':
            raise RuntimeError('Invalid objects.inv file version.')

        # next line is "# Project: <name>"
        # then after that is "# Version: <version>"
        projname = stream.readline().rstrip()[11:]
        version = stream.readline().rstrip()[11:]

        # next line says if it's a zlib header
        line = stream.readline()
        if 'zlib' not in line:
            raise RuntimeError('Invalid objects.inv file, not z-lib compatible.')

        # This code mostly comes from the Sphinx repository.
        entry_regex = re.compile(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)')
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, prio, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(':')
            if directive == 'py:module' and name in result:
                # From the Sphinx Repository:
                # due to a bug in 1.1 and below,
                # two inventory entries are created
                # for Python modules, and the first
                # one is correct
                continue

            # Most documentation pages have a label
            if directive == 'std:doc':
                subdirective = 'label'

            if location.endswith('$'):
                location = location[:-1] + name

            key = name if dispname == '-' else dispname
            if subdirective == "label":
                key = "label:"+key

            result[key] = os.path.join(url, location)

        return result

    async def build_rtfm_lookup_table(self, to_index=None):
        v = await self.db.fetchall("SELECT * FROM default_rtfm")
        pages = await self.db.fetchall("SELECT * FROM pages")
        for gid, default in v:
            self.defaults[gid] = default

        cache = {}
        for quick, long, url in pages:
            self.pages[quick] = {"quick": quick, "long":long, "url":url}
            if quick != to_index:
                continue

            async with self.bot.session.get(url + '/objects.inv') as resp:
                if resp.status != 200:
                    raise commands.CommandError(f'Cannot build rtfm lookup table, try again later. (no objects.inv found at {url})')

                stream = SphinxObjectFileReader(await resp.read())
                cache[quick] = self.parse_object_inv(stream, url)
        if self._rtfm_cache is None:
            self._rtfm_cache = cache
        else:
            self._rtfm_cache.update(cache)

    async def do_rtfm(self, ctx, key, obj, labels=True, obvious_labels=False):
        if ctx.guild is not None and ctx.guild.id in self.defaults and key is None:
            key = self.defaults[ctx.guild.id]

        if obj is None:
            await ctx.send(self.pages[key]['url'])
            return

        cache = list(self._rtfm_cache[key].items())

        matches = finder(obj, cache, labels, key=lambda t: t[0], lazy=False)[:8]

        e = discord.Embed(colour=0x36393E)
        if len(matches) == 0:
            return await ctx.send('Could not find anything. Sorry.')

        e.title = f"{key}: {obj}"
        e.description = '\n'.join(f'[`{key.replace("label:", "") if not obvious_labels else key}`]({url})' for key, url in matches)
        await ctx.send(embed=e)

    @commands.group(aliases=['rtfd', "rtm", "rtd"], invoke_without_command=True, help="read-the-f*cking-docs!! see `!help rtfm`")
    async def rtfm(self, ctx, *, obj: str = None):
        """
        read-the-f*cking-docs!
        view the documentation of the modules available in `rtfm list`.
        use their *quick* name to access it in the rtfm command, as such:
        `rtfm py sys`
        you may pass the `--no-labels` flag to filter out labels, or the `--obvious` flag to make it obvious that something is a label
        """
        labels = True
        obvious_labels = False
        if obj is not None:
            if "--no-labels" in obj:
                labels = False
                obj = obj.replace("--no-labels", "")
            if "--obvious" in obj:
                obvious_labels = True
                obj = obj.replace("--obvious", "")
            from discord.ext.commands.view import StringView
            view = StringView(obj)
            key = view.get_word()  # check if the first arg is specifying a certain rtfm
            if key in self.pages:
                approved_key = key
                view.skip_ws()
                obj = view.read_rest().strip()
                if not obj: obj=None
            elif ctx.guild.id in self.defaults:
                approved_key = self.defaults[ctx.guild.id]
            else:
                raise errors.CommandInterrupt("No rtfm selected, and no default rtfm is set for your guild.")
        elif ctx.guild.id in self.defaults:
            approved_key = self.defaults[ctx.guild.id]
        else:
            raise errors.CommandInterrupt("No rtfm selected, and no default rtfm is set for your guild.")
        if self._rtfm_cache is None or approved_key not in self._rtfm_cache:
            async with ctx.typing():
                await self.build_rtfm_lookup_table(approved_key)
        self.usage[approved_key] = datetime.datetime.utcnow()
        await self.do_rtfm(ctx, approved_key, obj, labels, obvious_labels)

    @rtfm.command()
    async def list(self, ctx):
        """
        shows a list of the current documentation entries. you can use the short name to use the doc. ex: !rtfm py {insert thing here}
        """
        all_entries = await self.db.fetchall("SELECT * FROM pages")
        entries = [(a[0] + f" {'(loaded)' if a[0] in self._rtfm_cache else '(unloaded)'}", f"{a[1]}\n{a[2]}") for a in all_entries]
        pages = paginator.FieldPages(ctx, entries=entries)
        await pages.paginate()

    @rtfm.command()
    @checks.check_editor()
    async def default(self, ctx, default: str):
        """
        sets a default rtfm for your guild, so you don't need to type the docs prefix each time.
        requires the `Bot Editor` role or higher
        note that you can only have 1 default per guild.
        """
        if default not in self.pages:
            return await ctx.send(f"`{default}` is not a valid RTFM! If you wish to add one, please use `!rtfm add` to submit it for review")
        else:
            self.defaults[ctx.guild.id] = default
            await self.db.execute("INSERT INTO default_rtfm VALUES (?,?)", ctx.guild.id, default)
            await ctx.send(f"set the guild's default rtfm to `{self.pages[default]['long']}`")

    @rtfm.command(usage="")
    async def add(self, ctx, quick=None, long=None, url=None):
        """
        have some documentation you want to see here? use this command to submit it for review!
        there are a few requirements for your docs to be approved.
        - it **must** be created with Sphinx.
        - it must be on readthedocs.io/.com or pythonhosted.org
        the bot will dm you when your request is approved or denied.
        you will be prompted for the documentation information
        """
        if await ctx.bot.is_owner(ctx.author) and quick and long and url:
            if quick in self.pages:
                return await ctx.send("Already exists")
            await self.db.execute("INSERT INTO pages VALUES (?,?,?)", quick, long, url)
            self.pages[quick] = {"quick": quick, "long": long, "url": url}
            return await ctx.send("\U0001f44d")
        async def check_cancel(ctx, m):
            if "cancel" in m.content:
                raise errors.CommandInterrupt("aborting")
        await ctx.send(f"{ctx.author.mention} --> by adding documentation, you agree that you have read the rules to adding documentation. type cancel to abort the creation process")
        await ctx.send(f"please provide a quick default for your rtfm (used when not accessing your guild's default, max 7 characters)")
        msg = await ctx.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author, timeout=30)
        quick = await commands.clean_content().convert(ctx, msg.content)
        if len(quick) > 7:
            raise commands.CommandError("That's more than 7 characters!")
        await check_cancel(ctx, msg)
        if quick in self.pages:
            raise commands.CommandError("that rtfm already exists!")
        await ctx.send("now, please provide the full documentation name")
        msg = await ctx.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author, timeout=30)
        long = await commands.clean_content().convert(ctx, msg.content)
        await ctx.send("Now, provide the url to the documentation.")
        msg = await ctx.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author, timeout=30)
        url = await commands.clean_content().convert(ctx, msg.content)
        try:
            v = await self.bot.session.get(url.strip("/")+"/objects.inv") #type: aiohttp.ClientResponse
            if v.status == 404: raise commands.CommandError
        except commands.CommandError:
            raise errors.CommandInterrupt("Invalid url provided (no /objects.inv found). remember to remove the current page! ex. https://docs.readthedocs.io/latest")
        await self.db.execute("INSERT INTO waiting VALUES (?,?,?,?)", ctx.author.id, quick, long, url.strip("/"))
        chan = ctx.bot.get_channel(625461752792088587)
        e = discord.Embed()
        e.add_field(name="quick", value=quick)
        e.add_field(name="long", value=long)
        e.add_field(name="url", value=url)
        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        e.colour = discord.Color.orange()
        await chan.send(embed=e)
        await ctx.send(f"{ctx.author.mention} --> your docs have been submitted for review.")

    @rtfm.command(hidden=True)
    @commands.is_owner()
    async def approve(self, ctx, quick):
        v = await self.db.fetchrow("SELECT * FROM waiting WHERE quick IS ?", quick)
        if v is None:
            raise commands.CommandError(f"No waiting approvals found with quick path `{quick}`")
        uid, quick, long, url = v
        user = ctx.bot.get_user(uid)
        if not user:
            await ctx.send("user not found. Can't dm approval.")
        else:
            try:
                await user.send(f"Your request for Documentation `{quick}` has been approved.")
            except discord.Forbidden:
                await ctx.send("Users DMs are blocked. Can't dm approval")
        await ctx.send(f"approved docs `{quick}`")
        await self.db.execute("INSERT INTO pages VALUES (?,?,?)", quick, long, url)
        await self.db.execute("DELETE FROM waiting WHERE quick IS ?", quick)
        self.pages[quick] = {"quick": quick, "long": long, "url": url}

    @rtfm.command(hidden=True)
    @commands.is_owner()
    async def deny(self, ctx, quick: str, *, reason: str):
        v = await self.db.fetchrow("SELECT * FROM waiting WHERE quick IS ?", quick)
        if v is None:
            raise commands.CommandError(f"No waiting approvals found with quick path `{quick}`")
        uid, quick, long, url = v
        user = ctx.bot.get_user(uid)
        if not user:
            await ctx.send("user not found. Can't dm approval.")
        else:
            try:
                await user.send(f"Your request for Documentation `{quick}` has been denied. reason: `{reason}`")
            except discord.Forbidden:
                await ctx.send("Users DMs are blocked. Can't dm approval")
        await self.db.execute("DELETE FROM waiting WHERE quick IS ?", quick)

    @rtfm.command(hidden=True)
    @commands.is_owner()
    async def remove(self, ctx, quick: str):
        await self.db.execute("DELETE FROM pages WHERE quick IS ?", quick)
        if quick in self.pages:
            del self.pages[quick]
            return await ctx.send(f"removed `{quick}` from rtfm")
        await ctx.send(f"`{quick}` not found")

    @rtfm.before_invoke
    @default.before_invoke
    @list.before_invoke
    async def rtfm_pre(self, ctx):
        if not self.defaults:
            v = await self.db.fetchall("SELECT * FROM default_rtfm")
            for gid, default in v:
                self.defaults[gid] = default
            await self.build_rtfm_lookup_table(None) # caches all the pages

    @commands.command()
    async def rtfs(self, ctx, search):
        """
        gets the source for an object from the discord.py library
        """
        overhead = ""
        raw_search = search
        searches = []
        if "." in search:
            searches = search.split(".")
            search = searches[0]
            searches = searches[1:]
        get = getattr(discord, search, None)
        if get is None:
            get = getattr(_root_commands, search, None)
            if get is None:
                get = getattr(_root_tasks, search, None)
        if get is None:
            return await ctx.send(f"Nothing found under `{raw_search}`")
        if inspect.isclass(get) or searches:
            if searches:
                for i in searches:
                    last_get = get
                    get = getattr(get, i, None)
                    if get is None and last_get is None:
                        return await ctx.send(f"Nothing found under ")
                    elif get is None:
                        overhead = f"Couldn't find `{i}` under `{last_get.__name__}`, showing source for `{last_get.__name__}`\n\n"
                        get = last_get
                        break
        if isinstance(get, property):
            get = get.fget

        lines, firstlineno = inspect.getsourcelines(get)
        try:
            module = get.__module__
            location = module.replace('.', '/') + '.py'
        except AttributeError:
            location = get.__name__.replace(".", "/") + ".py"

        ret = f"https://github.com/Rapptz/discord.py/blob/v{discord.__version__}"
        final = f"{overhead}[{location}]({ret}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1})"
        await ctx.send(embed=ctx.embed_invis(description=final))
