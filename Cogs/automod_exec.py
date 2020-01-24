import re

import discord

from utils import btime
from utils import commands

CAPS = re.compile(r"[ABCDEFGHIJKLMNOPQRSTUVWXYZ]")

def setup(bot):
    bot.add_cog(AModCog(bot))

setup = setup

class AModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = bot.automod_states
        self.cooldown = commands.CooldownMapping(commands.Cooldown(5, 3, commands.BucketType.channel))

    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.bot.setup or not self.states:
            return
        if not message.guild or not hasattr(message.author, "guild") or not (message.guild.me.guild_permissions.manage_messages and message.guild.me.guild_permissions.administrator):
            return
        if not self.bot.guild_module_states.get(message.guild.id, {"automod":False})['automod'] or self.ignored(message.author) or message.author.bot:
            return
        for coro in self.tests.copy():
            if await coro(self, message):
                break

    def ignored(self, member):
        guild = member.guild
        if member.guild_permissions.administrator or guild.owner == member:
            return False
        return False

    async def run_banned_words(self, message):
        punishment = self.states.get(message.guild.id, {"banned_words_punishment":0})['banned_words_punishment']
        if punishment == 0:
            return
        badwords = self.states[message.guild.id]['banned_words']
        if not badwords:
            return
        for word in badwords:
            if word in message.content.lower():
                try:
                    await message.author.send("**HEY!** *YOU CAN'T SAY THAT*")
                except:
                    pass
                await self.exec_punishment(message, punishment, reason="Bad Words")
                return True
        return False

    async def run_message_spam(self, message):
        punishment = self.states.get(message.guild.id, {"message_spam_punishment": 0})['message_spam_punishment']
        if punishment == 0:
            return
        if self.cooldown.update_rate_limit(message):
            await message.channel.purge(limit=10, check=lambda m: m.author == message.author)
            e = commands.Embed(title="AutoMod Action")
            e.description = ""
            e.add_field(name="Purged Messages.", value="total: 10")
            ctx = await self.bot.get_context(message)
            delay = (await btime.UserFriendlyTime(default="ree").convert(ctx, "5h")).dt
            #role_id = self.bot.guild_module_states[message.guild.id]['muted']
            role_id = 0
            role = message.guild.get_role(role_id)
            if role is not None:
                await message.author.add_roles(discord.Object(id=role_id), reason="Message Spam")
                await self.bot.schedule_timer(message.guild.id, "mute", delay.timetuple(), user=message.author.id,
                                              reason="Message Spam",
                                              role_id=role_id)
                delta = btime.human_timedelta(delay, source=message.created_at)
                e.add_field(name="User Muted", value="Reason: " + "Message Spam", inline=False)
                e.add_field(name="Mute length", value=delta, inline=False)
            await self.exec_punishment(message, punishment if punishment != 3 else 2, reason="Spam", embed=e)
            return True
        return False

    async def run_mass_mentions(self, message):
        maxmentions = self.states.get(message.guild.id, {"mass_mentions_max":0})['mass_mentions_max']
        punishment = self.states.get(message.guild.id, {"mass_mentions_punishment": 0})['mass_mentions_punishment']
        if punishment == 0:
            return
        if len(message.mentions) > maxmentions:
            await self.exec_punishment(message, punishment, reason="Mass Mentions")
            return True
        return False


    async def run_all_caps(self, message):
        perc, punishment = self.states.get(message.guild.id, {"all_caps_percent": 0})['all_caps_percent'], self.states.get(message.guild.id, {"all_caps_punishment":0})['all_caps_punishment']
        if punishment == 0:
            return
        v = CAPS.findall(message.content)
        if len(v) >= len(message.content)*(perc/100) and len(message.content) > 5:
            await self.exec_punishment(message, punishment, reason="All caps")
            return True
        return False


    async def run_allow_links(self, message):
        punishment = self.states.get(message.guild.id, {"links_punishment": 0})['links_punishment']
        if punishment == 0:
            return
        if "https://" in message.content.lower():
            await self.exec_punishment(message, punishment,
                                  reason="links not allowed")
            return True
        return False


    async def run_allow_discord_invites(self, message):
        punishment = self.states.get(message.guild.id, {"invites_punishment": 0})['invites_punishment']
        if punishment == 0 or punishment is None:
            return
        if "discord.gg" in message.content.lower():
            await self.exec_punishment(message, punishment,
                                  reason="Discord invites not allowed")
            return True
        return False

    async def exec_punishment(self, message, level: int, reason: str = "AutoMod", mute_len: str = "5h", echo=True, embed=None):
        self.bot.logging_ignore.append(message.id)
        channel = self.states[message.guild.id]['channel']
        channel = self.bot.get_channel(channel)
        e = embed or discord.Embed(title="AutoMod")
        e.set_author(icon_url=self.bot.user.avatar_url, name="AutoMod Action")
        e.set_footer(text=str(message.author) + " | ID: "+str(message.author.id), icon_url=message.author.avatar_url)
        e.colour = discord.Color.red()
        if level == 1:
            # delete the message
            try:
                await message.delete()
                e.add_field(name="Message deleted", value="Reason: "+reason, inline=False)
            except:
                e.add_field(name="AutoMod alert", value=f"Failed to delete an automod violation:\n{message.author} - message id: {message.id}\n\n{message.content}")
        elif level == 2:
            # delete and warn
            try:
                await message.delete()
            except:
                pass
            self.bot.dispatch("on_warn", message.author, message.guild.me, reason, message.guild, automod=channel if channel else "AM")
            e.add_field(name="User Warned", value="Reason: "+reason, inline=False)
            await message.author.send("you have been warned in {0.name} for: {1}".format(message.guild, reason))
        elif level == 3:
            # delete and instant mute the user
            try:
                await message.delete()
            except:
                pass
            ctx = await self.bot.get_context(message)
            delay = await btime.UserFriendlyTime(default="ree").convert(ctx, mute_len, )
            delay = delay.dt
            role_id = self.bot.guild_module_states[message.guild.id]['muted']
            await message.author.add_roles(discord.Object(id=role_id), reason=reason)
            await self.bot.schedule_timer(message.guild.id, "mute", delay.timetuple(), user=message.author.id, reason=reason,
                                          role_id=role_id)
            delta = btime.human_timedelta(delay, source=message.created_at)
            e.add_field(name="User Muted", value="Reason: "+reason, inline=False)
            e.add_field(name="Mute length", value=delta, inline=False)
        elif level == 4:
            # delete and boot the user
            try:
                await message.delete()
            except: pass
            await message.guild.ban(message.author, reason)
            e.add_field(name="User Banned", value="Reason: "+reason, inline=False)
        e.add_field(name="Message:", value=message.content)
        if not echo:
            return
        if not channel:
            return
        await channel.send(embed=e)

    tests = [
        run_all_caps, run_allow_discord_invites, run_allow_links, run_banned_words,
        run_mass_mentions, run_mass_mentions, run_message_spam
    ]

