import asyncio
import datetime
import itertools
import math
import random
import re
from typing import Union

import discord
import humanize
import wavelink

from utils import commands
from utils.checks import check_module
from utils.errors import CommandInterrupt

RURL = re.compile(r'https?:\/\/(?:www\.)?.+')

def setup(bot):
    bot.add_cog(music(bot))

class Track(wavelink.Track):
    __slots__ = ('requester', 'channel', 'message')

    def __init__(self, id_, info, *, ctx=None):
        super(Track, self).__init__(id_, info)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.message = ctx.message

    @property
    def is_dead(self):
        return self.dead

def checker():
    return check_module("music")

class MusicQueue(asyncio.Queue):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._queue = []
        self.index = 0
        self.repeat_start = None

    def shuffle(self):
        if self.repeat_start is not None:
            n = self.repeat_start
        else:
            n = self.index
        shuffle = self._queue[n:]
        random.shuffle(shuffle)
        old = self._queue[:n]
        self._queue = old + shuffle

    def repeat(self) -> None:
        if self.repeat_start is not None:
            self.repeat_start = None
        else:
            self.repeat_start = self.index

    def _get(self) -> Track:
        if self.repeat_start is not None:
            diff = self.index - self.repeat_start
            self.index += 1
            if len(self._queue) <= self.index:
                self.index = self.repeat_start
            return self._queue[diff]

        else:
            r = self._queue[self.index]
            self.index += 1
            return r

    def empty(self) -> bool:
        if self.repeat_start is not None:
            if len(self._queue) <= self.index:
                self.index = self.repeat_start
        return len(self._queue) <= self.index

    @property
    def q(self):
        return self._queue[self.index:]

    @property
    def history(self):
        return self._queue[:self.index]

class Player(wavelink.Player):
    def __init__(self, bot, guild_id: int, node: wavelink.Node):
        super(Player, self).__init__(bot, guild_id, node)

        self.queue = MusicQueue()
        self.next_event = asyncio.Event()
        self.controller_channel_id = None

        self.volume = 100
        self.dj = None
        self.controller_message = None
        self.reaction_task = None
        self.update = False
        self.updating = False
        self.inactive = False
        self.repeating = False

        self.controls = {'⏯': 'rp',
                         '⏹': 'stop',
                         '⏭': 'skip',
                         '🔀': 'shuffle',
                         '🔂': 'repeat'}

        self.pauses = set()
        self.resumes = set()
        self.stops = set()
        self.shuffles = set()
        self.skips = set()
        self.repeats = set()

        self.eq = 'Flat'

        bot.loop.create_task(self.player_loop())
        bot.loop.create_task(self.updater())

    @property
    def is_playing(self):
        return self.is_connected and self.current is not None

    @property
    def entries(self):
        return self.queue.q

    def repeat(self):
        self.queue.repeat()

    def shuffle(self):
        self.queue.shuffle()

    async def updater(self):
        while not self.bot.is_closed():
            if self.update and not self.updating:
                self.update = False
                await self.invoke_controller()

            await asyncio.sleep(10)

    async def player_loop(self):
        await self.bot.wait_until_ready()

        await self.set_eq(wavelink.Equalizer.flat())
        # We can do any pre loop prep here...
        await self.set_volume(self.volume)

        while True:
            self.next_event.clear()

            self.inactive = False
            try:
                song = await asyncio.wait_for(self.queue.get(), timeout=180)
            except asyncio.TimeoutError:
                if self.controller_channel_id is not None:
                    await self.bot.get_channel(self.controller_channel_id).send(embed=discord.Embed(description="Leaving due to inactivity!", color=0x36393E), delete_after=7)
                return await self.destroy()
            if not song:
                continue

            self.current = song
            self.paused = False

            await self.play(song)

            # Invoke our controller if we aren't already...
            if not self.update:
                await self.invoke_controller()

            if not self.is_connected:
                return

            # Wait for TrackEnd event to set our event...
            await self.next_event.wait()

            # Clear votes...
            self.pauses.clear()
            self.resumes.clear()
            self.stops.clear()
            self.shuffles.clear()
            self.skips.clear()
            self.repeats.clear()

    async def invoke_controller(self, track: wavelink.Track = None, channel: discord.TextChannel=None):
        """Invoke our controller message, and spawn a reaction controller if one isn't alive."""
        streaming = "\U0001f534 streaming"
        if not track:
            track = self.current
        if not channel:
            channel = self.bot.get_channel(self.controller_channel_id)
        else:
            self.controller_channel_id = channel.id

        if self.updating:
            return

        self.updating = True
        stuff = f'Now Playing:```ini\n{track.title}\n\n' \
                f'[EQ]: {self.eq}\n' \
                f'[Presets]: Flat/Boost/Piano/Metal\n' \
                f'[Duration]: {datetime.timedelta(milliseconds=int(track.length)) if not track.is_stream else streaming}\n' \
                f'[Volume]: {self.volume}\n'
        embed = discord.Embed(title='Music Controller',
                              colour=0xffb347)
        embed.set_thumbnail(url=track.thumb)
        embed.add_field(name='Video URL', value=f'[Click Here!]({track.uri})')
        embed.add_field(name='Requested By', value=track.requester.mention)
        embed.add_field(name='Current DJ', value=self.dj.mention)

        if len(self.entries) > 0:
            data = '\n'.join(f'- {t.title[0:45]}{"..." if len(t.title) > 45 else ""}\n{"-"*10}'
                             for t in itertools.islice([e for e in self.entries if not e.is_dead], 0, 3, None))
            stuff += data
        embed.description = stuff + "```"
        if self.controller_channel_id is None:
            self.controller_channel_id = track.channel.id
        if self.controller_message and channel.id != self.controller_message.id:
            try:
                await self.controller_message.delete()
            except discord.HTTPException:
                pass

            self.controller_message = await channel.send(embed=embed)
        elif not await self.is_current_fresh(channel) and self.controller_message:
            try:
                await self.controller_message.delete()
            except discord.HTTPException:
                pass

            self.controller_message = await channel.send(embed=embed)
        elif not self.controller_message:
            self.controller_message = await channel.send(embed=embed)
        else:
            self.updating = False
            return await self.controller_message.edit(embed=embed, content=None)

        try:
            self.reaction_task.cancel()
        except Exception:
            pass

        self.reaction_task = self.bot.loop.create_task(self.reaction_controller())
        self.updating = False

    async def add_reactions(self):
        """Add reactions to our controller."""
        for reaction in self.controls:
            try:
                await self.controller_message.add_reaction(str(reaction))
            except discord.HTTPException:
                return

    async def reaction_controller(self):
        """Our reaction controller, attached to our controller.
        This handles the reaction buttons and it's controls.
        """
        self.bot.loop.create_task(self.add_reactions())

        def check(r, u):
            if not self.controller_message:
                return False
            elif str(r) not in self.controls.keys():
                return False
            elif u.id == self.bot.user.id or r.message.id != self.controller_message.id:
                return False
            elif u not in self.bot.get_channel(int(self.channel_id)).members:
                return False
            return True

        while self.controller_message:
            if self.channel_id is None:
                return self.reaction_task.cancel()

            react, user = await self.bot.wait_for('reaction_add', check=check)
            control = self.controls.get(str(react))

            if control == 'rp':
                if self.paused:
                    control = 'resume'
                else:
                    control = 'pause'

            try:
                await self.controller_message.remove_reaction(react, user)
            except discord.HTTPException:
                pass
            cmd = self.bot.get_command(control)

            ctx = await self.bot.get_context(react.message)
            ctx.author = user

            try:
                if cmd.is_on_cooldown(ctx):
                    pass
                if not await self.invoke_react(cmd, ctx):
                    pass
                else:
                    self.bot.loop.create_task(ctx.invoke(cmd))
            except Exception as e:
                ctx.command = self.bot.get_command('reactcontrol')
                await cmd.dispatch_error(ctx=ctx, error=e)

        await self.destroy_controller()

    async def destroy_controller(self):
        """Destroy both the main controller and it's reaction controller."""
        try:
            await self.controller_message.delete()
            self.controller_message = None
        except (AttributeError, discord.HTTPException):
            pass

        try:
            self.reaction_task.cancel()
        except Exception:
            pass

    async def invoke_react(self, cmd, ctx):
        if not cmd._buckets.valid:
            return True

        if not (await cmd.can_run(ctx)):
            return False

        bucket = cmd._buckets.get_bucket(ctx)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return False
        return True

    async def is_current_fresh(self, chan):
        """Check whether our controller is fresh in message history."""
        try:
            async for m in chan.history(limit=8):
                if m.id == self.controller_message.id:
                    return True
        except (discord.HTTPException, AttributeError):
            return False
        return False

class music(commands.Cog):
    """All the tunes \U0001f3b5"""
    hidden = False
    def __init__(self, bot):
        self.bot = bot

        if not hasattr(bot, 'wavelink'):
            self.bot.wavelink = wavelink.Client(bot)

        bot.loop.create_task(self.initiate_nodes())

    async def initiate_nodes(self):
        nodes = {key: {'host': v['host'],
                          'port': v['port'],
                          'rest_url': f"http://{v['host']}:{v['port']}",
                          'password': v['password'],
                          'identifier': v['ident'],
                          'region': 'us_central'} for key, v in self.bot.settings['lavalink_nodes'].items()}

        for n in nodes.values():
            try:
                node = await self.bot.wavelink.initiate_node(host=n['host'],
                                                             port=n['port'],
                                                             rest_uri=n['rest_url'],
                                                             password=n['password'],
                                                             identifier=n['identifier'],
                                                             region=n['region'],
                                                             secure=False)

                node.set_hook(self.event_hook)
            except:
                pass

    def event_hook(self, event):
        """Our event hook. Dispatched when an event occurs on our Node."""
        if isinstance(event, wavelink.TrackEnd):
            event.player.next_event.set()
        elif isinstance(event, wavelink.TrackException):
            print(event.error)

    def required(self, player, invoked_with):
        """Calculate required votes."""
        channel = self.bot.get_channel(int(player.channel_id))
        if invoked_with == 'stop':
            if len(channel.members) - 1 == 2:
                return 2

        return math.ceil((len(channel.members) - 1) / 2.5)

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if ctx.command.qualified_name == self.musicchannel.qualified_name:
            return True
        channels = await self.bot.db.fetchall("SELECT channel_id FROM music_channels WHERE guild_id IS ?", ctx.guild.id)
        if not channels:
            return True
        if ctx.channel.id in [x[0] for x in channels]:
            return True
        raise commands.CheckFailure("This isn't a music channel!")

    async def has_perms(self, ctx, **perms):
        """Check whether a member has the given permissions."""
        try:
            player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        except:
            return False
        if player.dj is None:
            player.dj = ctx.author
        if ctx.author.id == player.dj.id:
            return True

        ch = ctx.channel
        permissions = ch.permissions_for(ctx.author)

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        if not missing:
            return True

        return False

    async def vote_check(self, ctx, command: str):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        vcc = len(self.bot.get_channel(int(player.channel_id)).members) - 1
        votes = getattr(player, command + 's', None)

        if vcc < 3 and not ctx.invoked_with == 'stop':
            votes.clear()
            return True
        else:
            votes.add(ctx.author.id)

            if len(votes) >= self.required(player, ctx.invoked_with):
                votes.clear()
                return True
        return False

    async def do_vote(self, ctx, player, command: str):
        if ctx.author.id == 143090142360371200:
            return
        attr = getattr(player, command + 's', None)
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if ctx.author.id in attr:
            await ctx.send(f'{ctx.author.mention}, you have already voted to {command}!', delete_after=15)
        elif await self.vote_check(ctx, command):
            await ctx.send(f'Vote request for {command} passed!', delete_after=20)
            to_do = getattr(self, f'do_{command}')
            await to_do(ctx)
        else:
            await ctx.send(f'{ctx.author.mention}, has voted to {command} the song!'
                           f' **{self.required(player, ctx.invoked_with) - len(attr)}** more votes needed!',
                           delete_after=45)

    @commands.command(name='reactcontrol', hidden=True)
    async def react_control(self, ctx):
        """Dummy command for error handling in our player."""
        pass

    @commands.group(invoke_without_command=True)
    async def musicchannel(self, ctx):
        """
        view the channels you can use music commands in!
        """
        channels = await self.bot.db.fetchall("SELECT channel_id FROM music_channels WHERE guild_id IS ?", ctx.guild.id)
        if not channels:
            return await ctx.send("Music commands can be used in any channel!")
        channels = [self.bot.get_channel(x[0]) for x in channels if self.bot.get_channel(x[0]) is not None]
        channels = [x.mention for x in channels if x.permissions_for(ctx.author).read_messages]
        e = ctx.embed_invis(title="Music Channels")
        fmt = "\n> " + "\n> ".join(channels)
        e.description = f"Music commands can be used in any of the following channels!\n{fmt}"
        await ctx.send(embed=e)

    @musicchannel.command()
    @commands.check_editor()
    async def add(self, ctx, channel: commands.TextChannel):
        """
        Add a channel to the whitelisted channels for music commands.
        You need the `bot editor` role to use this command.
        """
        await self.bot.db.execute("INSERT INTO music_channels VALUES (?,?)", ctx.guild.id, channel.id)
        await ctx.send(f"Added {channel.mention} to whitelisted channels")

    @musicchannel.command()
    @commands.check_editor()
    async def remove(self, ctx, channel: commands.TextChannel):
        """
        removes a channel from the whitelisted channels for music commands.
        you ned the `bot editor` role to use this command.
        """
        exists = await self.bot.db.fetch("SELECT channel_id FROM music_channels WHERE guild_id IS ? AND channel_id IS ?;", ctx.guild.id, channel.id)
        if not exists:
            return await ctx.send("That channel is not whitelisted.")
        await self.bot.db.execute("DELETE FROM music_channels WHERE guild_id IS ? AND channel_id IS ?;", ctx.guild.id, channel.id)
        await ctx.send(f"Removed {channel.mention} from whitelisted channels")

    @commands.command(name='connect', aliases=['join', 'summon'])
    @checker()
    async def connect_(self, ctx, *, channel: discord.VoiceChannel = None):
        """Connect to voice.
        Parameters
        ------------
        channel: discord.VoiceChannel [Optional]
            The channel to connect to. If a channel is not specified, an attempt to join the voice channel you are in
            will be made.
        """
        try:
            self.bot.logging_ignore.append(ctx.message.id)
            await ctx.message.delete()
        except discord.HTTPException:
            self.bot.logging_ignore.remove(ctx.message.id)

        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise CommandInterrupt('No channel to join. Please either specify a valid channel or join one.')

        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if player.is_connected:
            if ctx.author.voice.channel == ctx.guild.me.voice.channel:
                return

        await player.connect(channel.id)
        player.controller_channel_id = ctx.channel.id

    @commands.command(name='play', aliases=['sing'])
    @commands.cooldown(1, 2, commands.BucketType.user)
    @checker()
    async def play_(self, ctx, *, query: str):
        """Queue a song or playlist for playback.
        can be a youtube link or a song name.
        """
        await ctx.trigger_typing()

        await ctx.invoke(self.connect_)
        query = query.strip('<>')

        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('Bob is not connected to voice. Please join a voice channel to play music.')

        if not player.dj:
            player.dj = ctx.author

        if not RURL.match(query):
            query = f'ytsearch:{query}'

        tracks = await self.bot.wavelink.get_tracks(query)
        if not tracks:
            return await ctx.send('No songs were found with that query. Please try again.')

        if isinstance(tracks, wavelink.TrackPlaylist):
            for t in tracks.tracks:
                await player.queue.put(Track(t.id, t.info, ctx=ctx))

            await ctx.send(f'```ini\nAdded the playlist {tracks.data["playlistInfo"]["name"]}'
                           f' with {len(tracks.tracks)} songs to the queue.\n```')
        else:
            track = tracks[0]
            await ctx.send(f'```ini\nAdded {track.title} to the Queue\n```', delete_after=15)
            await player.queue.put(Track(track.id, track.info, ctx=ctx))

    @commands.command(name='np', aliases=['current', 'currentsong'])
    @commands.cooldown(2, 15, commands.BucketType.user)
    @checker()
    async def now_playing(self, ctx):
        """
        Show the Current Song
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player or not player.is_connected or player.updating or player.update:
            return

        await player.invoke_controller(channel=ctx.channel)

    @commands.command(name='pause')
    @checker()
    async def pause_(self, ctx):
        """Pause the currently playing song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player:
            return

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if player.paused:
            return

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has paused the song as an admin or DJ.', delete_after=25)
            return await self.do_pause(ctx)

        await self.do_vote(ctx, player, 'pause')

    async def do_pause(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        player.paused = True
        await player.set_pause(True)

    @commands.command(name='resume')
    @checker()
    async def resume_(self, ctx):
        """Resume a currently paused song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if not player.paused:
            return

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has resumed the song as an admin or DJ.', delete_after=25)
            return await self.do_resume(ctx)

        await self.do_vote(ctx, player, 'resume')

    async def do_resume(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        await player.set_pause(False)

    @commands.command(name='skip', aliases=['next'])
    @commands.cooldown(5, 10, commands.BucketType.user)
    @checker()
    async def skip_(self, ctx):
        """Skip the current song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has skipped the song as an admin or DJ.', delete_after=25)
            return await self.do_skip(ctx)

        if player.current.requester.id == ctx.author.id:
            await ctx.send(f'The requester {ctx.author.mention} has skipped the song.')
            return await self.do_skip(ctx)

        await self.do_vote(ctx, player, 'skip')

    async def do_skip(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        await player.stop()

    @commands.command(name='stop', aliases=['dc', 'disconnect', 'shoo', 'begone'])
    @commands.cooldown(3, 30, commands.BucketType.guild)
    @checker()
    async def stop_(self, ctx):
        """Stop the player, disconnect and clear the queue.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has stopped the player as an admin or DJ.', delete_after=25)
            return await self.do_stop(ctx)

        await self.do_vote(ctx, player, 'stop')

    async def do_stop(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        await player.destroy_controller()
        await player.destroy()

    @commands.command(name='volume', aliases=['vol'])
    @commands.cooldown(1, 2, commands.BucketType.guild)
    @checker()
    async def volume_(self, ctx, *, value: int):
        """Change the player volume.
        Aliases
        ---------
            vol
        Parameters
        ------------
        value: [Required]
            The volume level you would like to set. This can be a number between 1 and 100.
        Examples
        ----------
        <prefix>volume <value>
            {ctx.prefix}volume 50
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if not 0 < value < 101:
            return await ctx.send('Please enter a value between 1 and 100.')

        if not await self.has_perms(ctx, manage_guild=True) and player.dj.id != ctx.author.id:
            if (len(ctx.author.voice.channel.members) - 1) > 2:
                return

        await player.set_volume(value)
        await ctx.send(f'Set the volume to **{value}**%', delete_after=7)

        if not player.updating and not player.update:
            await player.invoke_controller()

    @commands.command(name='queue', aliases=['q', 'que'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @checker()
    async def queue_(self, ctx):
        """Retrieve a list of currently queued songs.
        Aliases
        ---------
            que
            q
        Examples
        ----------
        <prefix>queue
            {ctx.prefix}queue
            {ctx.prefix}q
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        upcoming = list(itertools.islice(player.entries, 0, 10))

        if not upcoming:
            return await ctx.send('```\nNo more songs in the Queue!\n```', delete_after=15)

        fmt = '\n'.join(f'**`{str(song)}`**' for song in upcoming)
        embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt)

        await ctx.send(embed=embed)

    @commands.command(name='shuffle', aliases=['mix'])
    @commands.cooldown(2, 10, commands.BucketType.user)
    @checker()
    async def shuffle_(self, ctx):
        """Shuffle the current queue.
        Aliases
        ---------
            mix
        Examples
        ----------
        <prefix>shuffle
            {ctx.prefix}shuffle
            {ctx.prefix}mix
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if len(player.entries) < 3:
            return await ctx.send('Please add more songs to the queue before trying to shuffle.', delete_after=10)

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has shuffled the playlist as an admin or DJ.', delete_after=25)
            return await self.do_shuffle(ctx)

        await self.do_vote(ctx, player, 'shuffle')

    async def do_shuffle(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        player.shuffle()

        player.update = True

    @commands.command(name='repeat')
    @checker()
    async def repeat_(self, ctx):
        """Repeat the currently playing song.
        Examples
        ----------
        <prefix>repeat
            {ctx.prefix}repeat
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has repeated the song as an admin or DJ.', delete_after=25)
            return await self.do_repeat(ctx)

        await self.do_vote(ctx, player, 'repeat')

    async def do_repeat(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        player.repeat()

    @commands.command(name='vol_up', hidden=True)
    @checker()
    @commands.help_check(lambda c: False)
    async def volume_up(self, ctx):
        """
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        vol = int(math.ceil((player.volume + 10) / 10)) * 10

        if vol > 100:
            vol = 100
            await ctx.send('Maximum volume reached', delete_after=7)

        await player.set_volume(vol)
        player.update = True

    @commands.command(name='vol_down', hidden=True)
    @checker()
    @commands.help_check(lambda c: False)
    async def volume_down(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        vol = int(math.ceil((player.volume - 10) / 10)) * 10

        if vol < 0:
            vol = 0
            await ctx.send('Player is currently muted', delete_after=10)

        await player.set_volume(vol)
        player.update = True

    @commands.command(name='seteq', aliases=['eq'])
    @checker()
    async def set_eq(self, ctx, *, eq: str):
        """
        set the music EQ!

        Available EQ
        -------------
        - Flat
        - Boost
        - Metal
        - Piano
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')
        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if eq.upper() not in player.equalizers:
            return await ctx.send(f'`{eq}` - Is not a valid equalizer!\nTry Flat, Boost, Metal, Piano.')

        await player.set_eq(player.equalizers[eq.upper()])
        await ctx.send(f'The player Equalizer was set to - {eq.capitalize()}')

    @commands.command()
    async def history(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        if not player.queue.history:
            return await ctx.send("No history!")

        for track in player.queue.history:
            track

    @commands.command(aliases=["wavelink", "wl", "ll"])
    @checker()
    async def musicinfo(self, ctx):
        """Retrieve various Node/Server/Player information."""
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        node = player.node

        used = humanize.naturalsize(node.stats.memory_used)
        total = humanize.naturalsize(node.stats.memory_allocated)
        free = humanize.naturalsize(node.stats.memory_free)
        cpu = node.stats.cpu_cores

        fmt = f'**WaveLink:** `{wavelink.__version__}`\n\n' \
              f'Connected to `{len(self.bot.wavelink.nodes)}` nodes.\n' \
              f'Best available Node `{self.bot.wavelink.get_best_node().__repr__()}`\n' \
              f'`{len(self.bot.wavelink.players)}` players are distributed on nodes.\n' \
              f'`{node.stats.players}` players are distributed on server.\n' \
              f'`{node.stats.playing_players}` players are playing on server.\n\n' \
              f'Server Memory: `{used}/{total}` | `({free} free)`\n' \
              f'Server CPU: `{cpu}`\n\n' \
              f'Server Uptime: `{datetime.timedelta(milliseconds=node.stats.uptime)}`'
        await ctx.send(fmt)
