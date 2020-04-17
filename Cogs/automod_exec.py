import re
import datetime, time
import discord
from utils import btime, commands, objects

CAPS = re.compile(r"[ABCDEFGHIJKLMNOPQRSTUVWXYZ]")
LINKS = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
INVITE = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
CHARS_MAPPING = {
    "a": ("a", "@", "*", "4"),
    "i": ("i", "*", "l", "1"),
    "o": ("o", "*", "0", "@"),
    "u": ("u", "*", "v"),
    "v": ("v", "*", "u"),
    "l": ("l", "1"),
    "e": ("e", "*", "3"),
    "s": ("s", "$", "5"),
}

def apply_mapping(words: list):
    ret = []
    ret2 = []
    for word in words:
        reps = [c for c in CHARS_MAPPING if c in word]
        if reps:
            for char in reps:
                for rep in CHARS_MAPPING[char]:
                    ret.append(word.replace(char, rep))
                    ret2.append(f" {word.replace(char, rep)} ")

        ret.append(word)
        ret2.append(f" {word} ")

    return ret, ret2

with open("data/default_wordlist.txt") as f:
    badwords, ms_badwords = apply_mapping(f.read().splitlines())
    badwords_tup = tuple(badwords)

def setup(bot):
    bot.add_cog(AModExec(bot))

class AModExec(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = bot.automod_states
        self.long_cooldown = commands.CooldownMapping(commands.Cooldown(25, 15, commands.BucketType.channel))
        self.short_cooldown = commands.CooldownMapping.from_cooldown(8, 4, commands.BucketType.channel)

    @commands.Cog.listener()
    async def on_message(self, message: commands.Message):
        if not self.bot.setup or not self.states:
            return 1

        if not message.guild or not hasattr(message.author, "guild") or not \
                message.guild.me.guild_permissions.manage_messages or not \
                message.guild.me.guild_permissions.administrator:
            return 2

        if message.guild.id not in self.states:
            return 3

        if self.ignored(message, self.states[message.guild.id]):
            return 4

        for coro in self.tests.copy():
            if await coro(self, message, self.states[message.guild.id]):
                return True


    def ignored(self, message, state: objects.AutomodLevels):
        if message.author.bot:
            return True

        if message.channel.id in state.ignored_channels:
            return True

        for role in message.author.roles:
            if role.id in state.ignores_roles:
                return True

        return False

    async def run_banned_words(self, message, state: objects.AutomodLevels):
        punishment = state.words
        if punishment == 0:
            return False

        found = False

        if state.default_filter:
            if message.content.startswith(badwords_tup):
                found = True

            elif message.content.endswith(badwords_tup):
                found = True

            else:
                for i in ms_badwords:
                    if i in message.content:
                        found = True
                        break

        if state.regex is not None and state.bad_words:
            if not found and state.regex.search(message.content):
                found = True

            elif not found and message.content.startswith(tuple(state.bad_words)):
                found = True

        if found:
            try:
                await message.author.send(f"You can't say that in {message.guild.name}")
            except:
                pass

            embed = self.create_embed(message)
            msg, emoji = await self.do_punishment(message, delete=punishment>=1, mute=punishment>=2, kick=punishment>=3, ban=punishment>=4)
            embed.description = f"{emoji}\n{msg}"
            embed.add_field(name="Reason", value=f"**Bad Words:**\n{message.content}")
            await self.send_to_log_channel(message, embed)
            return True

        return False

    async def run_message_spam(self, message, state: objects.AutomodLevels):
        punishment = state.spam
        if punishment == 0:
            return

        triggered = False
        reason = ""
        purge_amount = 0

        if self.long_cooldown.update_rate_limit(message):
            triggered = True
            reason = "Sent 25 messages in 15 seconds"
            purge_amount = 25
            self.long_cooldown.get_bucket(message).reset()

        if self.short_cooldown.update_rate_limit(message):
            triggered = True
            reason = "Sent 8 messages in 4 seconds"
            purge_amount = 8
            self.short_cooldown.get_bucket(message).reset()

        if triggered:
            e = self.create_embed(message)
            fmt, emoji = await self.do_punishment(message, purge=True, purge_amount=purge_amount, ban=punishment>=4, kick=punishment>=3, mute=punishment>=2)
            e.description = f"{emoji}\n{fmt}"
            e.add_field(name="Reason", value=reason)
            await self.send_to_log_channel(message, embed=e)
            return True

        return False

    async def run_mass_mentions(self, message: commands.Message, state: objects.AutomodLevels):
        punishment = state.mass_mentions
        maxmentions = state.mass_mentions_amount
        if punishment == 0:
            return

        if len(message.mentions) > maxmentions:
            fmt, emoji = await self.do_punishment(message, delete=True, mute=punishment>=2, kick=punishment>=3, ban=punishment>=4)
            embed = self.create_embed(message)
            embed.description = f"{emoji}\n{fmt}"
            embed.add_field(name="Reason", value=f"Mentioned {len(message.mentions)} members in one message")
            await self.send_to_log_channel(message, embed)
            return True

        return False


    async def run_all_caps(self, message, state: objects.AutomodLevels):
        punishment = state.caps
        percent = state.caps_percent
        if punishment == 0:
            return

        v = CAPS.findall(message.content)
        if len(v) >= len(message.content)*(percent/100) and len(message.content) > 5:
            fmt, emoji = await self.do_punishment(message, delete=True, mute=punishment>=2, kick=punishment>=3, ban=punishment>=4)
            embed = self.create_embed(message)
            embed.description = f"{emoji}\n{fmt}"
            embed.add_field(name="Reason", value=f"Message with {round(len(v)/len(message.content)*100)}% caps")
            await self.send_to_log_channel(message, embed)
            return True

        return False


    async def run_allow_links(self, message, state: objects.AutomodLevels):
        punishment = state.links
        if punishment == 0:
            return

        links = LINKS.findall(message.content)

        if links:
            links = [link.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] for link in links]

            for link in links:
                if link in state.blacklisted_links:
                    fmt, emoji = await self.do_punishment(message, delete=True, mute=punishment>=2, kick=punishment>=3, ban=punishment>=4)
                    embed = self.create_embed(message)
                    embed.description = f"{emoji}\n{fmt}"
                    embed.add_field(name="Reason", value=f"Blacklisted Link:\n{message.content}")
                    await self.send_to_log_channel(message, embed)
                    return True

        return False


    async def run_allow_discord_invites(self, message, state: objects.AutomodLevels):
        punishment = state.invites
        if punishment == 0:
            return

        if INVITE.search(message.content):
            fmt, emoji = await self.do_punishment(message, delete=True, mute=punishment>=2, kick=punishment>=3, ban=punishment>=4)
            embed = self.create_embed(message)
            embed.description = f"{emoji}\n{fmt}"
            embed.add_field(name="Reason", value=f"Server Invite:\n{message.content}")
            await self.send_to_log_channel(message, embed)
            return True

        return False

    def create_embed(self, message):
        emb = commands.Embed()
        emb.title = "Automod"
        emb.colour = discord.Color.red()
        emb.timestamp = datetime.datetime.utcnow()
        emb.set_author(name=str(message.author), icon_url=str(message.author.avatar_url))
        emb.set_footer(text=f"User id: {message.author.id}")

        return emb

    async def send_to_log_channel(self, message, embed):
        channel = self.states[message.guild.id].channel
        channel = self.bot.get_channel(channel)
        if channel is None:
            return

        await channel.send(embed=embed)

    async def do_mute(self, target: commands.Member, until=None):
        role = target.guild.get_role(self.bot.guild_role_states[target.guild.id]['muted'])
        if not role:
            await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", target.guild.id, target.id,
                                      self.bot.user.id,
                                      "Automod: Failed to mute user (no mute role set up)", datetime.datetime.utcnow())
            return False
        try:
            await target.add_roles(role, reason=f"Automod muted user")
        except commands.HTTPException:
            await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", target.guild.id, target.id, self.bot.user.id,
                                  "Automod: Failed to mute user (missing manage roles permission)", datetime.datetime.utcnow())
            return False

        await self.bot.pg.execute("INSERT INTO moddata VALUES ($1,$2,$3,$4,$5)", target.guild.id, target.id, self.bot.user.id,
                                  "Automod: User Muted", datetime.datetime.utcnow())
        await self.bot.pg.execute("INSERT INTO mutes VALUES ($1,$2,$3);", target.guild.id, target.id, until)
        return True

    async def do_punishment(self, message, delete=False, purge=False, purge_amount: int=None, mute=False, mute_until: int=None, kick=False, ban=False):
        ret = ""
        emoji = ""
        if delete:
            try:
                await message.delete()
                self.bot.logging_ignore.append(message.id)
            except discord.HTTPException:
                ret += "Failed to delete message (missing permissions or already deleted)\n"

            else:
                ret += "Message deleted\n"
                emoji = "<:messagedelete:684549889182531604>"

        if mute and not (kick or ban):
            if await self.do_mute(message.author, mute_until):
                ret += "User Muted\n"
                emoji = "\U0001f507"
            else:
                ret += "Failed to mute user\n"

        if purge:
            try:
                await message.channel.purge(limit=purge_amount, check=lambda m: m.author.id == message.author.id)
            except commands.HTTPException:
                ret += "Failed to purge user's messages\n"
            else:
                ret += "Purged user's messages\n"

        if kick and not ban:
            try:
                await message.guild.kick(message.author, reason="Automod")
            except discord.HTTPException:
                ret += "Failed to kick user\n"
            else:
                ret += "User Kicked\n"
                emoji = "<:memberleave:684549880425087032>"

        if ban:
            try:
                await message.author.ban(reason="Automod")
            except commands.HTTPException:
                ret += "Failed to ban user\n"
            else:
                ret += "Banned User\n"
                emoji = "<:bancreate:684549908211957787>"

        return ret, emoji

    tests = [
        run_all_caps, run_allow_discord_invites, run_allow_links, run_banned_words,
        run_mass_mentions, run_mass_mentions, run_message_spam
    ]

