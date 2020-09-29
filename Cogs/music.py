import datetime
import math
import re

import discord
import traceback
import humanize
import wavelink

from utils import commands, paginator
from utils.checks import check_module
from utils.errors import CommandInterrupt
from utils.objects import Player, AutoPlayer, Track

RURL = re.compile(r'https?:\/\/(?:www\.)?.+')

def setup(bot):
    bot.add_cog(music(bot))

def check_no_automusic():
    def predicate(ctx):
        if not isinstance(ctx.player, AutoPlayer):
            return True
        raise commands.CommandError("You may not use this while in automusic mode")
    return commands.check(predicate)

def check_in_voice():
    def predicate(ctx):
        if not ctx.player.is_connected:
            raise commands.CommandError('I am not currently connected to voice!')

        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            raise commands.CommandError(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")
        return True
    return commands.check(predicate)

def checker():
    return check_module("music")


class music(commands.Cog):
    """All the tunes \U0001f3b5"""
    hidden = False
    def __init__(self, bot):
        self.bot = bot

        if not hasattr(bot, 'wavelink'):
            self.bot.wavelink = wavelink.Client(bot=bot)
        if not hasattr(bot, "cached_always_play"):
            self.bot.cached_always_play = self.always_plays = {}
            self.bot.loop.create_task(self.load_always_play())
        else:
            self.always_plays = self.bot.cached_always_play

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
            except Exception as e:
                traceback.print_exception(type(e), e, e.__traceback__)

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
        channels = await self.bot.pg.fetch("SELECT channel_id FROM music_channels WHERE guild_id = $1", ctx.guild.id)
        if not channels:
            return True

        if ctx.channel.id in [x['channel_id'] for x in channels]:
            return True
        raise commands.CheckFailure("This isn't a music channel!")

    async def has_perms(self, ctx, **perms):
        """Check whether a member has the given permissions."""
        try:
            player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        except:
            return False
        if await self.bot.is_owner(ctx.author):
            return True
        try:
            if player.dj is None:
                player.dj = ctx.author
            if ctx.author.id == player.dj.id:
                return True
        except:
            pass

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
    @check_no_automusic()
    async def musicchannel(self, ctx):
        """
        view the channels you can use music commands in!
        """
        channels = await self.bot.pg.fetch("SELECT channel_id FROM music_channels WHERE guild_id = $1", ctx.guild.id)
        if not channels:
            return await ctx.send("Music commands can be used in any channel!")

        channels = [self.bot.get_channel(x['channel_id']) for x in channels if self.bot.get_channel(x['channel_id']) is not None]
        channels = [x.mention for x in channels if x.permissions_for(ctx.author).read_messages]
        e = ctx.embed_invis(title="Music Channels")
        fmt = "\n> " + "\n> ".join(channels)
        e.description = f"Music commands can be used in any of the following channels!\n{fmt}"
        await ctx.send(embed=e)

    @musicchannel.command()
    @commands.check_editor()
    @check_no_automusic()
    async def add(self, ctx, channel: commands.TextChannel):
        """
        Add a channel to the whitelisted channels for music commands.
        You need the `bot editor` role to use this command.
        """
        await self.bot.pg.execute("INSERT INTO music_channels VALUES ($1,$2)", ctx.guild.id, channel.id)
        await ctx.send(f"Added {channel.mention} to whitelisted channels")

    @musicchannel.command()
    @commands.check_editor()
    @check_no_automusic()
    async def remove(self, ctx, channel: commands.TextChannel): # TODO: put this in !queue subgroup?
        """
        removes a channel from the whitelisted channels for music commands.
        you ned the `bot editor` role to use this command.
        """
        exists = await self.bot.pg.fetch("SELECT channel_id FROM music_channels WHERE guild_id = $1 AND channel_id = $2;", ctx.guild.id, channel.id)
        if not exists:
            return await ctx.send("That channel is not whitelisted.")
        await self.bot.pg.execute("DELETE FROM music_channels WHERE guild_id = $1 AND channel_id = $2;", ctx.guild.id, channel.id)
        await ctx.send(f"Removed {channel.mention} from whitelisted channels")

    @commands.command(name='connect', aliases=['join', 'summon'])
    @checker()
    @check_no_automusic()
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

        if player.is_connected and ctx.guild.me.voice is not None:
            if ctx.author.voice.channel == ctx.guild.me.voice.channel:
                return

        await player.connect(channel.id)
        player.controller_channel_id = ctx.channel.id

    @commands.command(aliases=['sing'])
    @commands.cooldown(1, 2, commands.BucketType.user)
    @checker()
    @check_no_automusic()
    async def play(self, ctx, *, query: str):
        """Queue a song or playlist for playback.
        can be a youtube link or a song name.
        """
        await self.play_(ctx, query)

    @commands.command()
    @commands.cooldown(1, 2, commands.BucketType.user)
    @checker()
    @commands.check_manager()
    @check_no_automusic()
    async def playnext(self, ctx, *, query):
        """
        Queue a song or playlist to be played next.
        can be a youtube link or a song name.
        You must have the `Community Manager` role or higher to use this command
        """
        await self.play_(ctx, query, appendleft=True)

    async def play_(self, ctx, query, appendleft=False):
        await ctx.trigger_typing()
        await ctx.invoke(self.connect_)
        query = query.strip('<>')
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('Bob is not connected to voice. Please join a voice channel to play music.')

        if not player.dj:
            player.dj = ctx.author

        tracks, data = await self._find_tracks(ctx, player, query)
        if tracks is None:
            return
        if isinstance(tracks, list):
            for i in tracks:
                if appendleft:
                    player.queue.putleft(i)
                else:
                    player.queue.put_nowait(i)
            await ctx.send(f'```ini\nAdded the playlist {data.data["playlistInfo"]["name"]}'
                           f' with {len(data.tracks)} songs to the queue.\n```')
        else:
            if appendleft:
                player.queue.putleft(Track(tracks.id, tracks.info, ctx=ctx))
            else:
                player.queue.put_nowait(Track(tracks.id, tracks.info, ctx=ctx))
            await ctx.send(f'```ini\nAdded {tracks.title} to the Queue\n```', delete_after=15)

    async def _find_tracks(self, ctx, player, query):
        if not RURL.match(query):
            query = f'ytsearch:{query}'

        try:
            tracks = await self.bot.wavelink.get_tracks(query)
        except KeyError:
            tracks = None

        if not tracks:
            await ctx.send('No songs were found with that query. Please try again.')
            return None, None

        if isinstance(tracks, wavelink.TrackPlaylist):
            return [Track(t.id, t.info, ctx=ctx) for t in tracks.tracks], tracks

        else:
            track = tracks[0]
            return Track(track.id, track.info, ctx=ctx), tracks

    @commands.command(name='np', aliases=['current', 'currentsong'])
    @commands.cooldown(2, 15, commands.BucketType.user)
    @checker()
    async def now_playing(self, ctx):
        """
        Show the Current Song
        """
        if not ctx.player or not ctx.player.is_connected or not ctx.player.is_playing:
            return await ctx.send("Nothing is currently playing")

        await ctx.player.now_playing(channel=ctx.channel)

    @commands.command(name='pause')
    @checker()
    @check_no_automusic()
    @check_in_voice()
    async def pause_(self, ctx):
        """
        Pause the currently playing song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player:
            return

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
    @check_no_automusic()
    @check_in_voice()
    async def resume_(self, ctx):
        """
        Resume a currently paused song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

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
    @check_in_voice()
    @check_no_automusic()
    async def skip_(self, ctx):
        """Skip the current song.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)


        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has skipped the song as an admin or DJ.', delete_after=25)
            return await self.do_skip(ctx)

        if not player.current:
            return await ctx.send("Nothing is currently playing")

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
    @check_in_voice()
    @check_no_automusic()
    async def stop_(self, ctx):
        """Stop the player, disconnect and clear the queue.
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)


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
    @check_in_voice()
    async def volume_(self, ctx, *, value: int):
        """Change the player volume.
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

        if not 0 < value < 101:
            return await ctx.send('Please enter a value between 1 and 100.')

        if not await self.has_perms(ctx, manage_guild=True):
            if (len(ctx.author.voice.channel.members) - 1) > 2:
                return

        await player.set_volume(value)
        await ctx.send(f'Set the volume to **{value}**%', delete_after=7)


    @commands.command(name='queue', aliases=['q', 'que'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @checker()
    async def queue_(self, ctx):
        """Retrieve a list of currently queued songs.
        Examples
        ----------
        <prefix>queue
        {ctx.prefix}queue
        {ctx.prefix}q
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        upcoming = player.entries

        if not upcoming:
            return await ctx.send('```\nNo more songs in the Queue!\n```', delete_after=15)

        if isinstance(player, Player):
            pages = paginator.Pages(ctx, entries=[f"`{song}` - {song.author} - requested by: {song.requester}" for song
                                              in upcoming], embed_color=0x36393E, title="Upcoming Songs")
        else:
            pages = paginator.Pages(ctx, entries=[f"`{song}` - {song.author}" for song
                                              in upcoming], embed_color=0x36393E, title="Upcoming Songs")

        await pages.paginate()

    @commands.command(name='shuffle', aliases=['mix'])
    @commands.cooldown(2, 10, commands.BucketType.user)
    @checker()
    @check_in_voice()
    @check_no_automusic()
    async def shuffle_(self, ctx):
        """Shuffle the current queue.
        Examples
        ----------
        <prefix>shuffle
            {ctx.prefix}shuffle
            {ctx.prefix}mix
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

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

        if not ctx.player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        if ctx.author.voice is None or ctx.author.voice.channel != ctx.guild.me.voice.channel:
            return await ctx.send(f"You must be connected to {ctx.guild.me.voice.channel.mention} to control music!")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f'{ctx.author.mention} has repeated the song as an admin or DJ.', delete_after=25)
            return await self.do_repeat(ctx)

        await self.do_vote(ctx, ctx.player, 'repeat')

    async def do_repeat(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        player.repeat()

    @commands.command(name='vol_up', hidden=True)
    @checker()
    @check_in_voice()
    @commands.help_check(lambda c: False)
    async def volume_up(self, ctx):
        """
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        vol = int(math.ceil((player.volume + 10) / 10)) * 10

        if vol > 100:
            vol = 100
            await ctx.send('Maximum volume reached', delete_after=7)

        await player.set_volume(vol)
        player.update = True

    @commands.command(name='vol_down', hidden=True)
    @checker()
    @check_in_voice()
    @commands.help_check(lambda c: False)
    async def volume_down(self, ctx):
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        vol = int(math.ceil((player.volume - 10) / 10)) * 10

        if vol < 0:
            vol = 0
            await ctx.send('Player is currently muted', delete_after=10)

        await player.set_volume(vol)
        player.update = True

    @commands.command(name='seteq', aliases=['eq'])
    @checker()
    @check_no_automusic()
    @check_in_voice()
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
        player = ctx.player

        if eq.upper() not in player.equalizers:
            return await ctx.send(f'`{eq}` - Is not a valid equalizer!\nTry Flat, Boost, Metal, Piano.')

        await player.set_eq(player.equalizers[eq.upper()])
        await ctx.send(f'The player Equalizer was set to - {eq.capitalize()}')

    @commands.command()
    @checker()
    @check_no_automusic()
    @check_in_voice()
    async def controller(self, ctx):
        """
        gives you a fancy music controller
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.current:
            return await ctx.send("nothing is currently playing")

        await player.invoke_controller()

    @commands.command()
    @checker()
    @check_no_automusic()
    async def history(self, ctx):
        """
        Shows the song history of the **current session**
        """
        player = self.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send('I am not currently connected to voice!')

        if not player.queue.history:
            return await ctx.send("No history!")

        pages = paginator.Pages(ctx, entries=[f"[{track}]({track.uri} \"{track.title}\")"
                                              f" - {track.author} {'| Requested by'+str(track.requester) if not isinstance(player, AutoPlayer) else ''}" for track in
                                              reversed(player.queue.history)],
                                embed_color=0x36393E,
                                title="Music History",
                                per_page=5
                                )
        await pages.paginate()

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
              f'Server Cores: `{cpu}`\n\n' \
              f'Server Uptime: `{datetime.timedelta(milliseconds=node.stats.uptime)}`'
        await ctx.send(fmt)

    async def load_always_play(self):
        plays = await self.bot.pg.fetch("SELECT guild_id, vc_id, tc_id, playlist FROM music_loopers WHERE enabled = true;")

        for gid, vcid, tcid, pl in plays:
            self.always_plays[gid] = (vcid, pl, tcid)

    @commands.Cog.listener("on_voice_state_update")
    async def check_users(self, member, *args):
        if member.bot:
            return

        if not self.bot.is_ready() or member.guild.id not in self.always_plays:
            return

        player = self.bot.wavelink.get_player(member.guild.id, cls=AutoPlayer)
        if not isinstance(player, AutoPlayer):
            await player.destroy()
            player = self.bot.wavelink.get_player(member.guild.id, cls=AutoPlayer)

        player.controller_channel_id = self.always_plays[member.guild.id][2]

        if not player.is_connected:
            try:
                await player.connect(self.always_plays[member.guild.id][0])
                await self.run_playlist(player, member.guild)

            except discord.Forbidden:
                return

            except discord.HTTPException:
                # channel not found?
                return  # TODO: maybe remove the mode here?

        if len(member.guild.me.voice.channel.members) == 1:
            if not player.paused:
                await player.set_pause(True)

        else:
            if player.paused:
                await player.set_pause(False)

    async def run_playlist(self, player: AutoPlayer, guild, playlist=None):
        player.autoplay = True
        playlist = playlist or self.always_plays[guild.id][2]
        try:
            tracks = await self.bot.wavelink.get_tracks(playlist) #type: wavelink.TrackPlaylist
        except Exception as e:
            tracks = None
        if not tracks:
            try:
                await self.bot.get_channel(self.always_plays[guild.id][1]).send(
                    f"Failed to load playlist at <{self.always_plays[guild.id][2]}")
            finally:
                return

        player.assign_playlist(tracks.tracks, tracks.data)

    @commands.group("247", invoke_without_command=True)
    @commands.check_editor()
    @checker()
    async def twofortyseven(self, ctx, voice_channel: discord.VoiceChannel, text_channel: discord.TextChannel, playlist: str):
        tracks = await self.bot.wavelink.get_tracks(playlist)

        if not tracks:
            return await ctx.send("Invalid playlist")

        await self.bot.pg.execute("INSERT INTO music_loopers VALUES ($1,$2,$3,$4,$5) ON CONFLICT (guild_id) DO UPDATE "
                                  "SET playlist=$4, vc_id=$2, tc_id=$3 WHERE music_loopers.guild_id=$1;", ctx.guild.id,
                                  voice_channel.id, text_channel.id, playlist, False)

        await ctx.send(f"Your 24/7 music has been set up. To enable it, run `{ctx.prefix}247 enabled`")

    @twofortyseven.command("enable")
    @commands.check_editor()
    @checker()
    async def tfs_enable(self, ctx):
        await self.tfs_runner(ctx, True)

    @twofortyseven.command("disable")
    @commands.check_editor()
    @checker()
    async def tfs_disable(self, ctx):
        await self.tfs_runner(ctx, False)

    async def tfs_runner(self, ctx, state: bool):
        found = await self.bot.pg.fetchrow("UPDATE music_loopers SET enabled=$1 WHERE guild_id = $2 RETURNING guild_id, vc_id, tc_id, playlist;",
                                        state, ctx.guild.id)

        if not found:
            return await ctx.send("Please set up 24/7 music first")

        else:
            await ctx.send(f"{'Enabled' if state else 'Disabled'} 24/7 music")

        if state:
            self.always_plays[ctx.guild.id] = found['vc_id'], found['tc_id'], found['playlist']

        else:
            self.always_plays.pop(ctx.guild.id, None)

        try:
            await ctx.player.destroy()
        except:
            pass
