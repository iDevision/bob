from utils import commands
import datetime
import asyncio

def setup(bot):
    bot.add_cog(BT(bot))


class BT(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bt_webhook = commands.Webhook.from_url(
            "https://discordapp.com/api/webhooks/666875784744534035/fOQp2LBNN28DEU5__wCrmni3jaD_cTttq2uCRZZQjCAMbulAUyN4ny3o7KHqor3HiWqG",
            adapter=commands.AsyncWebhookAdapter(self.bot.session))
        self.bob_webhook = commands.Webhook.from_url(
            "https://discordapp.com/api/webhooks/666878596492689408/h-2HB5gDrsNaOpF81gJE_0vPirnbTrsI__Turqd-B_7nmujau4jRHCjDS9_U5sNO52as",
            adapter=commands.AsyncWebhookAdapter(self.bot.session))

    async def cog_check(self, ctx):
        if not await ctx.bot.is_owner(ctx.author):
            raise commands.NotOwner("Nope")
        return True

    @commands.group(invoke_without_command=True)
    async def bugbot(self, ctx):
        pass

    @bugbot.group(invoke_without_command=True, aliases=['scripts'])
    async def script(self, ctx):
        pass

    @script.command("track")
    async def s_track(self, ctx, scriptname, *, issue):
        prev = await self.bot.db.fetchall("SELECT * FROM bt_bugs")
        e = commands.Embed(color=commands.Color.red(), title=f"Issue #{len(prev)+1} - {scriptname}", description=issue, timestamp=datetime.datetime.utcnow())
        e.set_footer(text="Issue registered at")
        msg = await self.bt_webhook.send(embed=e, wait=True)
        await self.bot.db.execute("INSERT INTO bt_bugs VALUES (?,?,?,?,?,0)", len(prev)+1, msg.id, scriptname, issue, datetime.datetime.utcnow().timestamp())
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass

    @script.command("release")
    async def s_release(self, ctx: commands.Context, errorid: int):
        data = await self.bot.db.fetchrow("SELECT * FROM bt_bugs WHERE id = ?;", errorid)
        if data is None:
            await ctx.send(f"No script bug found with id {errorid}")
            await asyncio.sleep(5)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        emb = commands.Embed(color=commands.Color.dark_green(), title=f"Issue #{errorid} - {data[2]} (Fixed)", description=data[3])
        emb.timestamp = datetime.datetime.utcnow()
        emb.set_footer(text="Issue released at")
        await self.bot.http.delete_message(self.bt_webhook.channel_id, data[1], reason=f"Bug Fixed (#{errorid})")
        msg = await self.bt_webhook.send(embed=emb, wait=True)
        await self.bot.db.execute("UPDATE bt_bugs SET msgid=?, resolved=1;", msg.id)

    @bugbot.group()
    async def bob(self, ctx):
        pass

    @bob.command()
    async def track(self, ctx: commands.Context, scriptname, *, issue):
        prev = await self.bot.db.fetchall("SELECT * FROM bob_bugs;")
        e = commands.Embed(color=commands.Color.red(), title=f"Bug #{len(prev) + 1} - {scriptname}", description=issue,
                      timestamp=datetime.datetime.utcnow())
        e.set_footer(text="Bug registered at")
        msg = await self.bob_webhook.send(embed=e, wait=True)
        await self.bot.db.execute("INSERT INTO bob_bugs VALUES (?,?,?,?,0)", len(prev) + 1, msg.id, issue,
                                  datetime.datetime.utcnow().timestamp())
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass

    @bob.command()
    async def release(self, ctx: commands.Context, errorid: int):
        data = await self.bot.db.fetchrow("SELECT * FROM bob_bugs WHERE id = ?", errorid)
        if data is None:
            await ctx.send(f"No bug found with id {errorid}", delete_after=5)
            await asyncio.sleep(5)
            try:
                await ctx.message.delete()
            except:
                pass
            return
        emb = commands.Embed(color=commands.Color.dark_green(), title=f"Bug #{errorid} - {data[2]} (Fixed)",
                        description=data[3])
        emb.timestamp = datetime.datetime.utcnow()
        emb.set_footer(text="Issue released at")
        await self.bot.http.delete_message(self.bt_webhook.channel_id, data[1], reason=f"Bug Fixed (#{errorid})")
        msg = await self.bob_webhook.send(embed=emb, wait=True)
        await self.bot.db.execute("UPDATE bt_bugs SET msgid=?, resolved=1;", msg.id)
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass

