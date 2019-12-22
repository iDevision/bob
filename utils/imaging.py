import asyncio
import io
import os

import discord
from PIL import Image

from runtimeinfo import INSTALL_DIR as idir

avy_bg = os.path.join(idir, "data", "photos", "avy_bg2.jpg")

async def aio_create_profile_card(ctx, user, points, total_msg, warnings):
    pfp = Image.frombuffer('RGBA', (128,128), await user.avatar_url_as(format="jpeg").read())
    loop = asyncio.get_running_loop()
    file = await loop.run_in_executor(None, create_profile_card, pfp, str(user), points, total_msg, warnings)
    await ctx.send(file=file)

def create_profile_card(pfp, name, points, total_msg, warnings):
    bg = Image.open(avy_bg, 'r')
    img_w, img_h = pfp.size
    bg_w, bg_h = bg.size
    offset = ((bg_w - img_w) // 2, (bg_h - img_h) // 2)
    bg.paste(pfp, offset)
    buf = io.BytesIO()
    bg.save(buf, format='JPEG')
    return discord.File(buf)
