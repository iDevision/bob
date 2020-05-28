from utils import commands
from PIL import Image, ImageDraw, ImageFont
import io, asyncio, traceback, multiprocessing
import os

def setup(bot):
    bot.add_cog(Imaging(bot))

class Imaging(commands.Cog):
    category = "misc"
    def __init__(self, bot):
        self.bot = bot
        self.install = os.path.dirname(os.path.dirname(__file__))
        self.avy_bg = os.path.join(self.install, "data", "photos", "profile_bg.jpeg")

    @commands.command("profile")
    @commands.check_module("basics")
    @commands.cooldown(1, 15, commands.BucketType.member)
    @commands.check(lambda ctx: ctx.guild.id == 336642139381301249)
    async def profile_get(self, ctx: commands.Context, target: commands.Member = None):
        """
        gets your server profile card
        """
        target = target or ctx.author
        points, warns = 500,0
        await self.aio_create_profile_card(ctx, target, points, warns)

    async def aio_create_profile_card(self, ctx, user, points, warnings):
        try:
            async with ctx.typing():
                pfp = io.BytesIO(await user.avatar_url_as(format="png", size=256).read())
                pfp.seek(0)
                card = await self.bot.loop.run_in_executor(None, self.create_profile_card, pfp, user, points, warnings)
                await ctx.send(file=card)
        except Exception as e:
            traceback.print_exception(type(e),e,e.__traceback__)

    def create_profile_card(self, pfp: io.BytesIO, user, points, warnings):
        #pfp = Image.open(pfp)
        bg = Image.open(self.avy_bg, 'r')
        #pfp.resize((img_w*2, img_h*2))
        #pfp, mask = self._add_corners(pfp)
        #pfp = pfp.copy()
        #bg.paste(pfp, (50, 50), mask)
        self.add_text(bg, user, points, warnings)
        buf = io.BytesIO()
        bg.save(buf, format='png')
        buf.seek(0)
        bg.close()
        return commands.File(buf, filename="pfp.png")

    def _add_corners(self, image, rad=130):
        circle = Image.new("L", (rad * 2, rad * 2))
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
        alpha = Image.new("L", image.size, 255)
        w, h = image.size
        alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
        alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
        alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
        alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
        image.putalpha(alpha)
        return image, alpha

    def add_text(self, img, user, points, warns):
        fnt = ImageFont.truetype(os.path.join(self.install, "data", "Dreamstar.otf"), 120)
        fnt2 = ImageFont.truetype(os.path.join(self.install, "data", "Dreamstar.otf"), 150)
        d = ImageDraw.Draw(img)
        f = f"""
    {points} Points | {warns} Warnings
        """"".strip()
        roles = " | ".join([x.name for x in user.roles])
        d.text((50, 250), f, font=fnt, fill=user.color.to_rgb())
        d.text((50, 130), str(user), font=fnt2, fill=(27, 227, 233))
        d.text((50, 350), roles, font=fnt, fill=(27, 227, 233))
