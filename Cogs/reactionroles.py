from utils import commands, checks

def setup(bot):
    bot.add_cog(_reactionroles(bot))

class _reactionroles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.pg
        self.category = "settings"

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if self.bot.get_user(payload.user_id).bot:
            return
        if not payload.guild_id:
            return
        s = await self.db.fetchrow("SELECT role_id, mode FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji_id = $3",
                               payload.guild_id, payload.message_id, payload.emoji.name if payload.emoji.is_unicode_emoji() else str(payload.emoji.id))
        if s is None:
            return

        match, mode = s
        if match and mode in [1,3]:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            try:
                await member.add_roles(commands.Object(id=match))
            except commands.HTTPException: pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        s = await self.db.fetchrow(
            "SELECT role_id, mode FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji_id = $3",
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

        lnk = await ctx.ask("please respond with a link to the message you wish to add the reaction role to.", return_bool=False)

        try:
            msg = await commands.MessageConverter().convert(ctx, lnk)
        except:
            return await ctx.send("couldnt find a message at that link. Aborting (check that i have perms in that channel)")

        v = await ctx.send("please add a reaction (the emote **must** be from this server, or a built in emote) to **this** message. it will be used as the reaction role emote")

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
        await self.db.execute("INSERT INTO reaction_roles VALUES ($1,$2,$3,$4,$5,$6);", ctx.guild.id, role.id, str(emote.id) if is_custom else emote, msg.id, msg.channel.id, mode)
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

        v = await self.db.execute("DELETE FROM reaction_roles WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji_id = $4",
                              ctx.guild.id, channel.id, msg.id, str(emote.id) if is_custom else emote)
        await ctx.send("if there was a reaction role there, it is now a thing of the past!")
