from utils import commands
import datetime
import asyncio

def setup(bot):
    bot.add_cog(BT(bot))


class BT(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bt_webhook = commands.Webhook.from_url(bot.settings['scripts_bugbot_url'],
            adapter=commands.AsyncWebhookAdapter(self.bot.session))
        self.bob_webhook = commands.Webhook.from_url(bot.settings['bob_bugbot_url'],
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
        prev = await self.bot.pg.fetch("SELECT * FROM bt_bugs")
        e = commands.Embed(color=commands.Color.red(), title=f"Issue #{len(prev)+1} - {scriptname}", description=issue, timestamp=datetime.datetime.utcnow())
        e.set_footer(text="Issue registered at")
        msg = await self.bt_webhook.send(embed=e, wait=True)
        await self.bot.pg.execute("INSERT INTO bt_bugs VALUES ($1,$2,$3,$4,$5,false)", len(prev)+1, msg.id, scriptname, issue, datetime.datetime.utcnow().timestamp())
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass

    @script.command("release")
    async def s_release(self, ctx: commands.Context, errorid: int):
        data = await self.bot.pg.fetchrow("SELECT * FROM bt_bugs WHERE id = $1;", errorid)
        if not data:
            await ctx.send(f"No script bug found with id {errorid}")
            await asyncio.sleep(5)
            try:
                await ctx.message.delete()
            finally:
                return
        emb = commands.Embed(color=commands.Color.dark_green(), title=f"Issue #{errorid} - {data[2]} (Fixed)", description=data[3])
        emb.timestamp = datetime.datetime.utcnow()
        emb.set_footer(text="Issue released at")
        await (await self.bot.get_channel(666875639164436521).fetch_message(data[1])).delete()
        msg = await self.bt_webhook.send(embed=emb, wait=True)
        await self.bot.pg.execute("UPDATE bt_bugs SET msgid=$1, resolved=true WHERE id=$2;", msg.id, errorid)

    @bugbot.group()
    async def bob(self, ctx):
        pass

    @bob.command()
    async def track(self, ctx: commands.Context, scriptname, *, issue):
        prev = await self.bot.pg.fetch("SELECT * FROM bob_bugs;")
        e = commands.Embed(color=commands.Color.red(), title=f"Bug #{len(prev) + 1} - {scriptname}", description=issue,
                      timestamp=datetime.datetime.utcnow())
        e.set_footer(text="Bug registered at")
        msg = await self.bob_webhook.send(embed=e, wait=True)
        await self.bot.pg.execute("INSERT INTO bob_bugs VALUES ($1,$2,$3,$4,false)", len(prev) + 1, msg.id, issue,
                                  datetime.datetime.utcnow().timestamp())
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass

    @bob.command()
    async def release(self, ctx: commands.Context, errorid: int):
        data = await self.bot.pg.fetchrow("SELECT * FROM bob_bugs WHERE id = $1;", errorid)
        if not data:
            await ctx.send(f"No bug found with id {errorid}", delete_after=5)
            await asyncio.sleep(5)
            try:
                await ctx.message.delete()
            finally:
                return

        emb = commands.Embed(color=commands.Color.dark_green(), title=f"Bug #{errorid} - {data[2]} (Fixed)",
                        description=data[2])
        emb.timestamp = datetime.datetime.utcnow()
        emb.set_footer(text="Issue released at")
        await (await self.bot.get_channel(666878516469563402).fetch_message(data[1])).delete()
        msg = await self.bob_webhook.send(embed=emb, wait=True)
        await self.bot.pg.execute("UPDATE bt_bugs SET msgid=$1, resolved=true WHERE id=$2;", msg.id, errorid)
        await ctx.message.add_reaction("\U0001f44d")
        await asyncio.sleep(5)
        try:
            await ctx.message.delete()
        except:
            pass
