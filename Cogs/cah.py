import datetime
import json
import os
import random
import time

import discord

import runtimeinfo
from utils import checks
from utils import commands

cahdecks = os.path.join(runtimeinfo.INSTALL_DIR, "data", "cahdecks")
available_decks = {"Base Deck": "base", "First Expansion": "expansion1", "Second Expansion": "expansion2",
                   "Third Expansion": "expansion3", "Fourth Expansion": "expansion4", "Fifth Expansion": "expansion5",
                   "Sixth Expansion": "expansion6", "MegaPack": "largedeck"}
def setup(bot):
    bot.add_cog(cah(bot))

class Deck:
    def __init__(self, deck: str):
        with open(os.path.join(cahdecks, f"cah_{deck}.json")) as f:
            self._deck = json.load(f)
        self.usable = self._deck.copy()
        self.discarded = {"blackCards": [], "whiteCards": []}

    def get_black_card(self)->tuple:
        while True:
            c = random.choice(self.usable['blackCards'])
            self.discarded['blackCards'].append(c)
            self.usable['blackCards'].remove(c)
            if c['pick'] <= 2:
                break
        return c['text'], c['pick']

    def get_white_card(self)->str:
        c = random.choice(self.usable['whiteCards'])
        self.discarded['whiteCards'].append(c)
        self.usable['whiteCards'].remove(c)
        return c


class Hand:
    def __init__(self, user: discord.User, deck: Deck):
        self.deck = deck
        self.user = user
        self.slots = dict((e, "") for e in range(1, 10))
        self.points = 0
        self.timeout = 300
        self.last_msg = time.time()
        self.new_hand()

    def new_hand(self):
        for i in self.slots:
            self.slots[i] = self.deck.get_white_card()

    async def card_used(self,msg: discord.Message, num: int, num2:int=None):
        if num not in self.slots or num2 not in self.slots:
            return None, discord.Embed(title="Invalid Card!", color=discord.Color.red())

        sel = self.slots[num]
        self.slots[num] = self.deck.get_white_card()
        if num2 is not None:
            sel2 = self.slots[num2]
            self.slots[num2] = self.deck.get_white_card()
            return (sel, sel2), None
        return sel, None

    async def format_hand(self):
        e = discord.Embed(title="**Your Hand**", color=discord.Color.teal())
        e.set_author(name=self.user.name, icon_url=self.user.avatar_url)
        v = ""
        for n, i in self.slots.items():
            v += f"#{n} - {i}\n"
        e.description = v.strip()
        return e

class cah(commands.Cog):
    """
    allows for some good ol' games of Cards Against Humanity.
    """
    category = "fun"
    walk_on_help = True
    def __init__(self, bot):
        self.bot = bot
        self.group = "Fun"
        self.games = {}  # we are not storing games in a database. fuck that.
        self.users_in_games = {}  # to ensure users are only in one game at a time

    def cog_check(self, ctx):
        if ctx.guild is None:
            return True
        return checks.check_module("fun")

    async def format_embed(self, game, embed: discord.Embed=None):
        embed = embed or discord.Embed()
        embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f"CAH game id: {game['id']}")
        return embed

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.guild is not None or msg.author.id not in self.users_in_games:
            return
        if msg.content.startswith("!") or msg.content.startswith("?"):
            return
        await self.broadcast_user_msg(msg)

    async def broadcast_user_msg(self, msg: discord.Message):
        gameid = self.users_in_games[msg.author.id]
        users = self.games[gameid]['users']
        e = await self.format_embed(self.games[gameid], discord.Embed(color=discord.Color.blue()))
        e.set_author(name=str(msg.author), icon_url=msg.author.avatar_url)
        e.description = msg.content
        if msg.attachments:
            # im hoping that people dont send non-pictures...
            e.set_image(url=msg.attachments[0].url)
        for user in users.keys():
            await user.send(embed=e)

    async def broadcast_system_msg(self, game, embed):
        embed = await self.format_embed(game, embed)
        for user in game['users'].keys():
            await user.send(embed=embed)

    async def broadcast_tzar_msg(self, game, tzar, blackcard, pick):
        e = await self.format_embed(game, None)
        e.color = discord.Color.from_rgb(0,0,0)
        e.set_author(name=str(tzar), icon_url=tzar.avatar_url)
        e.title = f"{tzar} is the card Tzar!"
        e.add_field(name="The Card", value=blackcard)
        e.add_field(name="pick", value=f"**{pick}**", inline=False)
        for user in game['users'].keys():
            if user == tzar:
                continue
            await user.send(embed=e)
        e.title = "You are the card Tzar!"
        await tzar.send(embed=e)

    @commands.group("cah", invoke_without_command=True)
    async def cah_new_game(self, ctx: commands.Context):
        """
        starts a new game of cards against humanity.
        friends can join using `!cah join <game id>` !
        note that you can only be in one game at a time.
        """
        if ctx.author.id in self.users_in_games:
            return await ctx.send(f"{ctx.author.mention} --> you can only be in one game at a time!")
        gamenum = random.randint(5000, 1000000)
        while gamenum in self.games:
            # theoretically, this shouldnt loop more than once or twice.
            gamenum = random.randint(5000, 1000000)
        self.users_in_games[ctx.author.id] = gamenum
        self.games[gamenum] = game = {"users": {}, "deck": Deck("largedeck"), "blackcard": None, "tzar": None, "id": gamenum,
                                      "entries": {}, "blacksels": 0, "order": [], "index": -1, "pickable": False, "choosable": False,
                                      "running": False}
        game['users'][ctx.author] = {"hand": Hand(ctx.author, game['deck'])}
        game['order'].append(ctx.author)

        await self.broadcast_system_msg(game, discord.Embed(title="Waiting for players (1/3)", description="Use `!help cah` to find the playing commands!"))
        await ctx.send(f"created new cards against humanity game with id `{gamenum}`\nEveryone can join with `{ctx.invoked_with}cah join {gamenum}` !")

    @cah_new_game.command()
    async def join(self, ctx, gamenum: int):
        """
        join a game of cards against humanity!
        """
        if not gamenum in self.games:
            return await ctx.send("That game does not exist!")
        self.games[gamenum]['users'][ctx.author] = {"hand": Hand(ctx.author, self.games[gamenum]['deck'])}
        self.bot.dispatch("cah_user_join", ctx.author, self.games[gamenum])


    @commands.Cog.listener()
    async def on_cah_user_join(self, user, game):
        e = await self.format_embed(game, None)
        e.colour = discord.Color.green()
        if len(game['users']) <= 3:
            e.title = f"User Joined! ({len(game['users'])}/3)"
        else:
            e.title = f"User Joined!"
        e.description = str(user)
        await self.broadcast_system_msg(game, e)
        if len(game['users']) >= 3 and not game['running']:
            game['running'] = True
            await self.rotate(game)

    async def rotate(self, game):
        # the game positioning, message sending, etc will happen here
        index = game['index']
        if index+1 >= len(game['order']):
            index = 0
        else:
            index += 1
        tzar = game['order'][index]
        game['tzar'] = tzar
        blackcard, picks = game['deck'].get_black_card()
        await self.broadcast_tzar_msg(game, tzar, blackcard, picks)
        for user in game['users']:
            if user == tzar:
                continue
            await user.send(embed=await game[user]['hand'].format_hand())


    @commands.command(usage="<choices>")
    @commands.dm_only()
    async def pick(self, ctx, num: int, num2: int=None):
        """
        allows you to pick what cards you're going to play. if you are playing multiple cards, you should separate the numbers with a space.
        usage:
          !pick 1 3
        would pick cards 1 and 3 from your hand.
        Alternatively, as the card Tzar, this allows you to select the winning card (s)
        """
        if ctx.author.id not in self.users_in_games:
            return await ctx.send("you are not in a CAH game!")
        game = self.games[self.users_in_games[ctx.author.id]]
        if game['tzar'] == ctx.author:
            return await self.choose(ctx, num)
        if num not in range(1, 10):
            return await ctx.send("Invalid Choice!")

        if game['blacksels'] == 2 and not num2:
            return await ctx.send("You need to pick 2 cards!")
        if game['blacksels'] == 1 and num2 is not None:
            return await ctx.send("Too many card selections!")
        cards, embed = await game['users'][ctx.author]['hand'].card_used(ctx, num, num2)
        if embed is not None:
            embed = self.format_embed(game, embed)
            return await ctx.send(embed=embed)
        e = await self.format_embed(game, None)
        e.color = discord.Color.magenta()
        e.title = "You chose"
        if game['blacksels'] == 2:
            e.description = f"`{cards[0]}`\n`{cards[1]}`"
        else:
            e.description = f"`{cards}`"
        game['entries'][ctx.author] = cards
        await ctx.send(embed=e)
        if len(game['entries']) >= len(game['users']-1):
            await self.tzar_turn(game)
    pick.brief = "See `!help cah pick`"

    async def tzar_turn(self, game):
        e = await self.format_embed(game, None)
        e.title = "Selections!"
        e.description = f"The card Tzar ({game['tzar']}) will now pick the winner"
        v = 1
        for user, entries in game['entries'].items():
            if game['blacksels'] == 2:
                e.add_field(name=str(v), value=f"{entries[0]}  |  {entries[1]}", inline=False)
            else:
                e.add_field(name=str(v), value=entries, inline=False)
            v += 1
        await self.broadcast_system_msg(game, e)

    async def choose(self, ctx, num: int):
        if not ctx.author.id in self.users_in_games:
            return await ctx.send("You're not in a CAH game!")
        game = self.games[self.users_in_games[ctx.author.id]]
        if ctx.author != game['tzar']:
            return await ctx.send("You're not the card Tzar!")
        if num not in range(1, len(game['entries'])):
            return await ctx.send("Invalid choice!")
        for i, user in enumerate(game['entries']):
            if i == num:
                embed = await self.format_embed(game, None)
                embed.color = discord.Color.green()
                embed.title = f"The card Tzar has chosen number {i} ({user})"
                await self.broadcast_system_msg(game, embed)
                break
        e = await self.format_embed(game, None)
        e.color = discord.Color.orange()
        v = 1
        for user, entries in game['entries'].items():
            if game['blacksels'] == 2:
                e.add_field(name=f"{v} | {user}", value=f"{entries[0]}  |  {entries[1]}", inline=False)
            else:
                e.add_field(name=str(v), value=entries, inline=False)
            v += 1
        await self.broadcast_system_msg(game, e)

    @cah_new_game.command()
    @commands.dm_only()
    async def leave(self, ctx):
        if not ctx.author.id in self.users_in_games:
            return await ctx.send("You're not in a CAH game!")
        gamenum = self.users_in_games[ctx.author.id]
        del self.users_in_games[ctx.author.id]
        del self.games[gamenum]['users'][ctx.author]
        e = discord.Embed(title="User left", description=str(ctx.author), color=discord.Color.red())
        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        await ctx.author.send(embed=e)
        if len(self.games[gamenum]['users']) == 0:
            del self.games[gamenum]  # the game is over
            return
        await self.broadcast_system_msg(self.games[gamenum], e)
