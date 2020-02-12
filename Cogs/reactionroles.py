from utils import commands, checks

def setup(bot):
    bot.add_cog(reactionroles(bot))

class reactionroles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id:
            return
        s = await self.db.fetchrow("SELECT role_id, mode FROM reaction_roles WHERE guild_id IS ? AND message_id IS ? AND emoji_id IS ?",
                               payload.guild_id, payload.message_id, payload.emoji.name if payload.emoji.is_unicode_emoji() else str(payload.emoji.id))
        if s is None:
            return
        match, mode = s
        if match and mode in [1,3]:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            await member.add_roles(commands.Object(id=match))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        s = await self.db.fetchrow(
            "SELECT role_id, mode FROM reaction_roles WHERE guild_id IS ? AND message_id IS ? AND emoji_id IS ?",
            payload.guild_id, payload.message_id,
            payload.emoji.name if payload.emoji.is_unicode_emoji() else str(payload.emoji.id))
        if s is None:
            return
        match, mode = s
        if match and mode in [2, 3]:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            await member.remove_roles(commands.Object(id=match))

    @commands.group(aliases=['rr'])
    async def reactionrole(self, ctx):
        """
        allows for the creation of reaction roles! react on a message, get the corresponding role!
        Use `reactionrole add` to add a new reaction role!
        """
        pass

    @reactionrole.command(aliases=["+"])
    @checks.check_editor()
    async def add(self, ctx):
        """
        Adds a new reaction role.
        Only works with the manage roles permission and the add reactions permission.
        This command will guide you through the process of adding a reaction role.
        You must have the `bot editor` role to use this command
        """
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send("I need the `manage roles` permission to enable reaction roles!")
        if not ctx.guild.me.guild_permissions.add_reactions:
            return await ctx.send("I need the `add reactions` permission to enable reaction roles!")
        v = await ctx.ask("please respond with the mode you wish to set this reaction role to.\n```\n1: add on reaction\n2: remove on reaction\n3:add on reaction, remove on reaction removal\n```", return_bool=False)
        try:
            mode = int(v.strip())
            if mode not in [1,2,3]: raise ValueError
        except:
            return await ctx.send("not a number, or invalid number. aborting")
        role = await ctx.ask("please respond with the role you wish to add", return_bool=False)
        try:
            role = await commands.RoleConverter().convert(ctx, role)
        except:
            return await ctx.send("role unrecognized. aborting")
        channel = await ctx.ask("please respond with the channel your reaction message is in", return_bool=False)
        try:
            channel = await commands.TextChannelConverter().convert(ctx, channel)
        except:
            return await ctx.send("channel unrecognized. aborting")
        msgid = await ctx.ask("please respond with the **id** of the message you wish to add the reaction role to.", return_bool=False)
        try:
            msg = await channel.fetch_message(int(msgid))
        except:
            return await ctx.send("couldnt find a message with that id, or the conversion to integer failed. aborting")
        v = await ctx.send("please add a reaction (the emote **must** be from this server) to **this** message. it will be used as the reaction role emote")
        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=lambda r, u: u==ctx.author and r.message.id == v.id, timeout=60)
            if isinstance(reaction.emoji, (commands.PartialEmoji, commands.Emoji)):
                if reaction.emoji not in ctx.guild.emojis:
                    raise ValueError
            emote = reaction.emoji
            is_custom = reaction.custom_emoji
        except:
            return await ctx.send("Invalid, aborting")
        await msg.add_reaction(emote)
        await self.db.execute("INSERT INTO reaction_roles VALUES (?,?,?,?,?,?)", ctx.guild.id, role.id, str(emote.id) if is_custom else emote, msgid, channel.id, mode)
        await ctx.send("complete! your reaction role should now add as reacted")

    @reactionrole.command()
    @commands.check_editor()
    async def remove(self, ctx):
        """
        removes a reaction role.
        you must have the `bot editor` role to use this command
        """
        try:
            channel = await commands.TextChannelConverter().convert(ctx, await ctx.ask("please respond with the channel your reaction role is in", return_bool=False))
        except:
            return await ctx.send("invalid channel. aborting")
        try:
            msgid = await ctx.ask("please respond with the message **id** of the reaction role you wish to remove", return_bool=False)
            msg = await channel.fetch_message(int(msgid))
        except:
            return await ctx.send("invalid message id, or not a number")
        v = await ctx.send("please react to **this** message with the reaction you wish to remove")
        try:
            reaction, user = await self.bot.wait_for("reaction_add",
                                                     check=lambda r, u: u == ctx.author and r.message.id == v.id,
                                                     timeout=60)
            if isinstance(reaction.emoji, (commands.PartialEmoji, commands.Emoji)):
                if reaction.emoji not in ctx.guild.emojis:
                    raise ValueError
            emote = reaction.emoji
            is_custom = reaction.custom_emoji
        except:
            return await ctx.send("Invalid, aborting")
        v = await self.db.execute("DELETE FROM reaction_roles WHERE guild_id IS ? AND channel_id IS ? AND message_id IS ? AND emoji_id IS ?",
                              ctx.guild.id, channel.id, msg.id, str(emote.id) if is_custom else emote)
        await ctx.send("if there was a reaction role there, it is now a thing of the past!")
