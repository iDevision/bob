# credit to danny for the reading of sphinx.
import io
import os
import re
import zlib

import discord

from utils import checks, errors, paginator
from utils import db, commands


def setup(bot):
    bot.add_cog(_rtfm(bot))

def finder(text, collection, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
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
        self._rtfm_cache = None

    def parse_object_inv(self, stream, url):
        # key: URL
        # n.b.: key doesn't have `discord` or `discord.ext.commands` namespaces
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

            if projname == 'discord.py':
                key = key.replace('discord.ext.commands.', '').replace('discord.', '')

            result[key] = os.path.join(url, location)

        return result

    async def build_rtfm_lookup_table(self):
        v = await self.db.fetchall("SELECT * FROM default_rtfm")
        pages = await self.db.fetchall("SELECT * FROM pages")
        for gid, default in v:
            self.defaults[gid] = default

        cache = {}
        for quick, long, url in pages:
            self.pages[quick] = {"quick": quick, "long":long, "url":url}
            sub = cache[quick] = {}
            async with self.bot.session.get(url + '/objects.inv') as resp:
                if resp.status != 200:
                    raise RuntimeError('Cannot build rtfm lookup table, try again later.')

                stream = SphinxObjectFileReader(await resp.read())
                cache[quick] = self.parse_object_inv(stream, url)

        self._rtfm_cache = cache

    async def do_rtfm(self, ctx, key, obj):
        if ctx.guild.id in self.defaults and key is None:
            key = self.defaults[ctx.guild.id]


        if obj is None:
            await ctx.send(self.pages[key]['url'])
            return

        obj = re.sub(r'^(?:discord\.(?:ext\.)?)?(?:commands\.)?(.+)', r'\1', obj)

        if key.startswith('dpy'):
            # point the abc.Messageable types properly:
            q = obj.lower()
            for name in dir(discord.abc.Messageable):
                if name[0] == '_':
                    continue
                if q == name:
                    obj = f'abc.Messageable.{name}'
                    break

        cache = list(self._rtfm_cache[key].items())

        def transform(tup):
            return tup[0]

        matches = finder(obj, cache, key=lambda t: t[0], lazy=False)[:8]
        #matches = difflib.get_close_matches(obj, cache, 8)

        e = discord.Embed(colour=discord.Colour.teal())
        if len(matches) == 0:
            return await ctx.send('Could not find anything. Sorry.')

        e.description = '\n'.join(f'[`{key}`]({url})' for key, url in matches)
        await ctx.send(embed=e)

    @commands.group(aliases=['rtfd', "rtm", "rtd"], invoke_without_command=True)
    async def rtfm(self, ctx, *, obj: str = None):
        """
        read-the-f*cking-docs!! see `!help rtfm`
        """
        if obj is not None:
            from discord.ext.commands.view import StringView
            view = StringView(obj)
            key = view.get_quoted_word()  # check if the first arg is specifying a certain rtfm
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
        await self.do_rtfm(ctx, approved_key, obj)

    @rtfm.command()
    async def list(self, ctx):
        """
        shows a list of the current documentation entries. you can use the short name to use the doc. ex: !rtfm py lalaall
        """
        entries = [(self.pages[a]['quick'], f"{self.pages[a]['long']}\n\n{self.pages[a]['url']}") for a in self.pages]
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

    @rtfm.command()
    async def add(self, ctx):
        """
        have some documentation you want to see here? use this command to submit it for review!
        there are a few requirements for your docs to be approved.
        - it **must** be created with Sphinx.
        - it must be on readthedocs.io/.com or pythonhosted.org
        the bot will dm you when your request is approved or denied.
        """
        async def check_cancel(ctx, m):
            if "cancel" in m.content:
                raise errors.CommandInterrupt("aborting")
        await ctx.send(f"{ctx.author.mention} --> by adding documentation, you agree that you have read the rules to adding documentation. type cancel to abort the creation process")
        await ctx.send(f"{ctx.author.mention} --> please provide a quick default for your rtfm (used when not accessing your guild's default, max 7 characters)")
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
            await self.bot.session.get(url+"/objects.inv")
        except:
            raise errors.CommandInterrupt("Invalid url provided. remember to remove the current page! ex. https://docs.readthedocs.io/latest")
        await self.db.execute("INSERT INTO waiting VALUES (?,?,?,?)", ctx.author.id, quick, long, url)
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
        await self.build_rtfm_lookup_table()

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


    @rtfm.before_invoke
    @default.before_invoke
    @list.before_invoke
    async def rtfm_pre(self, ctx):
        if not self._rtfm_cache:
            await ctx.trigger_typing()
            await self.build_rtfm_lookup_table()