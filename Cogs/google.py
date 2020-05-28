# borrowed from Belphegor

import asyncio
import functools
import re
from urllib.parse import quote

import aiohttp
import discord
from bs4 import BeautifulSoup as BS
import typing, random

from utils import commands
from utils.errors import GoogleError
from utils.paginator import Pages

#==================================================================================================================================================

SUPERSCRIPT = {
    "0": "0x2070",
    "1": "0x00b9",
    "2": "0x00b2",
    "3": "0x00b3",
    "4": "0x2074",
    "5": "0x2075",
    "6": "0x2076",
    "7": "0x2077",
    "8": "0x2078",
    "9": "0x2079"
}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Safari/537.36"

#==================================================================================================================================================
MAX_FILE_SIZE = 1024 * 1024 * 20
TIMEOUT = 20
NO_IMG = "http://i.imgur.com/62di8EB.jpg"
CHUNK_SIZE = 512 * 1024
def _error_handle(func):
    @functools.wraps(func)
    async def new_func(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.TimeoutError:
            raise GoogleError("Cannot retrieve file. Please try again.")
        except aiohttp.InvalidURL:
            raise GoogleError("Invalid URL.")
    return new_func

@_error_handle
async def fetch(session, url, *, max_file_size=MAX_FILE_SIZE, timeout=TIMEOUT, **options):
    headers = options.pop("headers", {"User-Agent": USER_AGENT})
    async with session.get(url, headers=headers, timeout=timeout, **options) as response:
        stream = response.content
        data = []
        current_size = 0
        async for chunk in stream.iter_chunked(CHUNK_SIZE):
            current_size += len(chunk)
            if current_size > max_file_size:
                break
            else:
                data.append(chunk)
        if stream.at_eof():
            return b"".join(data)
        else:
            raise GoogleError(f"File size limit is {max_file_size/1024/1024:.1f}MB.")

def discord_escape(any_string):
    discord_regex = re.compile(r"[*_\[\]~`\\<>]")
    return discord_regex.sub(lambda m: f"\\{m.group(0)}", any_string)

def safe_url(any_url):
    return quote(any_url, safe=r":/&$+,;=@#~%?")

class _fun(commands.Cog):
    category="fun"
    walk_on_help = False
    def __init__(self, bot):
        self.group = "fun"
        self.bot = bot
        self.latest_xkcd = 2281
        self.google_session = aiohttp.ClientSession()
        self.google_lock = asyncio.Lock()
        self.google_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, sdch",
            "Connection": "keep-alive",
            "User-Agent": USER_AGENT
        }

    def cog_unload(self):
        self.bot.create_task_and_count(self.google_session.close())

    @commands.command()
    @commands.cooler()
    @commands.check_module('fun')
    async def xkcd(self, ctx, num_or_latest: typing.Union[int, str]=None):
        """
        some good ol' xkcd webcomics
        """
        num = num_or_latest
        if num is None:
            num = f"/{random.randint(1, 2260)}"
        elif isinstance(num, str):
            if num in ['latest', 'newest', 'l', 'n']:
                num = ""
            else:
                return await ctx.send("psst, the (optional) argument needs to be a number, or 'latest'/'l'")
        else:
            if num > self.latest_xkcd:
                return await ctx.send(f"hey, that one doesnt exist! try `{ctx.prefix}xkcd latest`")
            num = f"/{num}"
        async with self.bot.session.get(f"https://xkcd.com{num}/info.0.json") as r:
            resp = await r.json()
            if not num:
                self.latest_xkcd = resp['num']
            e = commands.Embed(name=resp['safe_title' if ctx.channel.is_nsfw() else "title"], description=resp['alt'], color=0x36393E)
            e.set_footer(text=f"#{resp['num']}  • {resp['month']}/{resp['day']}/{resp['year']}")
            e.set_image(url=resp['img'])
            await ctx.send(embed=e)

    @commands.command()
    @commands.cooler()
    @commands.check_module('fun')
    async def dadjoke(self, ctx):
        """
        terrible jokes, anyone?
        """
        resp = await self.bot.session.get("https://icanhazdadjoke.com", headers={"Accept": "text/plain"})
        await ctx.send((await resp.content.read()).decode("utf-8 "))

    def _parse_google(self, html):
        soup = BS(html, "lxml")
        for script in soup("script"):
            script.decompose()

        search_results = []
        all_tags = soup.find_all(lambda x: x.name=="div" and x.get("class")==["g"] and len(x.attrs)==1)
        for tag in all_tags:
            a = tag.find("a")
            h3 = a.find("h3")
            if h3:
                title = h3.text
            else:
                title = a.text
            search_results.append((title, a["href"]))
            if len(search_results) > 4:
                break

        #video
        tag = soup.find("div", class_="FGpTBd")
        if tag:
            other = "\n\n".join([f"<{t[1]}>" for t in search_results[:4]])
            return f"**Search result:**\n{tag.find('a')['href']}\n\n**See also:**\n{other}"

        g_container = soup.find(lambda x: x.name=="div" and "obcontainer" in x.get("class", []))
        if g_container:
            #unit convert
            try:
                results = g_container.find_all(True, recursive=False)
                embed = discord.Embed(title="Search result:", description=f"**Unit convert - {results[0].find('option', selected=1).text}**", colour=discord.Colour.dark_orange())
                embed.add_field(name=results[1].find("option", selected=1).text, value=results[1].find("input")["value"])
                embed.add_field(name=results[3].find("option", selected=1).text, value=results[3].find("input")["value"])
                if search_results:
                    embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[:4])), inline=False)
                return embed
            except:
                pass

            #timezone convert
            zone_data = g_container.find("div", class_="sL6Rbf")
            if zone_data:
                try:
                    text = []
                    for stuff in zone_data.find_all(True, recursive=False):
                        table = stuff.find("table")
                        if table:
                            for tr in table.find_all(True, recursive=False):
                                text.append(tr.get_text())
                        else:
                            text.append(stuff.get_text().strip())
                    outtxt = "\n".join(text)
                    embed = discord.Embed(
                        title="Search result:",
                        description=f"**Timezone**\n{outtxt}",
                        colour=discord.Colour.dark_orange()
                    )
                    if search_results:
                        embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[:4])), inline=False)
                    return embed
                except:
                    pass

            #currency convert
            input_value = g_container.find("input", id="knowledge-currency__src-input")
            input_type = g_container.find("select", id="knowledge-currency__src-selector")
            output_value = g_container.find("input", id="knowledge-currency__tgt-input")
            output_type = g_container.find("select", id="knowledge-currency__tgt-selector")
            if all((input_value, input_type, output_value, output_type)):
                try:
                    embed = discord.Embed(title="Search result:", description="**Currency**", colour=discord.Colour.dark_orange())
                    embed.add_field(name=input_type.find("option", selected=1).text, value=input_value["value"])
                    embed.add_field(name=output_type.find("option", selected=1).text, value=output_value["value"])
                    if search_results:
                        embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[:4])), inline=False)
                    return embed
                except:
                    pass

            #calculator
            inp = soup.find("span", class_="cwclet")
            out = soup.find("span", class_="cwcot")
            if inp or out:
                try:
                    embed = discord.Embed(title="Search result:", description=f"**Calculator**\n{inp.text}\n\n {out.text}", colour=discord.Colour.dark_orange())
                    if search_results:
                        embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[:4])), inline=False)
                    return embed
                except:
                    pass

        #wiki
        tag = soup.find("div", class_="knowledge-panel")
        if tag:
            try:
                title = tag.find("div", class_="kno-ecr-pt").span.text
                desc = tag.find("div", class_="kno-rdesc")
                img_box = tag.find("div", class_="kno-ibrg")
                if desc:
                    url_tag = desc.find("a")
                    if url_tag:
                        url = f"\n[{url_tag.text}]({safe_url(url_tag['href'])})"
                    else:
                        url = ""
                    description = f"**{title}**\n{desc.find('span').text.replace('MORE', '').replace('…', '')}{url}"
                else:
                    description = f"**{title}**"
                embed = discord.Embed(title="Search result:", description=description, colour=discord.Colour.dark_orange())
                try:
                    raw_img_url = URL(img_box.find("a")["href"])
                    img_url = raw_img_url.query.get("imgurl", "")
                    if img_url.startswith(("http://", "https://")):
                        embed.set_thumbnail(url=img_url)
                except:
                    pass
                embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[:4])), inline=True)
                return embed
            except:
                pass

        #definition
        tags = soup.find_all("div", class_="lr_dct_ent")
        if tags:
            try:
                defines = []
                for tag in tags:
                    top_box = tag.find("div", class_="Jc6jBf")
                    gsrt = top_box.find("div", class_="gsrt")
                    name = gsrt.find("span").text
                    pronounce = top_box.find("div", class_="lr_dct_ent_ph").text
                    for relevant in tag.find("div", class_="vmod").find_all("div", class_="vmod", recursive=False):
                        form_tag = relevant.find("div", class_="vk_gy")
                        form = []
                        for ft in form_tag.find_all("span", recursive=False):
                            for child in ft.children:
                                if child.name == "b":
                                    text = f"*{child.text}*"
                                elif child.name is None:
                                    text = child
                                else:
                                    text = child.text
                                if text:
                                    form.append(text)

                        page = [f"**{name}**", pronounce, "\n", "".join(form)]
                        definition_box = relevant.find("ol", class_="lr_dct_sf_sens")
                        for each in definition_box.find_all("li", recursive=False):
                            deeper = each.find("div", class_="lr_dct_sf_sen")
                            number = deeper.find("div", style="float:left")
                            list_of_definitions = "\n".join(f"- {t.text}" for t in deeper.find_all("div", attrs={"data-dobid": "dfn"}))
                            page.append(f"**{number.text}**\n{list_of_definitions}")

                        defines.append("\n".join(page))

                see_also = "\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[1:5]))
                embeds = []
                max_page = len(defines)
                for i, d in enumerate(defines):
                    embed = discord.Embed(title="Search result:", description=f"{defines[i]}\n\n(Page {i+1}/{max_page})", colour=discord.Colour.dark_orange())
                    embed.add_field(name="See also:", value=see_also, inline=False)
                    embeds.append(embed)
                return embeds
            except:
                import traceback
                traceback.print_exc()

        #weather
        tag = soup.find("div", class_="card-section", id="wob_wc")
        if tag:
            try:
                more_link = tag.next_sibling.find("a")
                embed = discord.Embed(
                    title="Search result:",
                    description=f"**Weather**\n[{more_link.text}]({safe_url(more_link['href'])})",
                    colour=discord.Colour.dark_orange()
                )
                embed.set_thumbnail(url=f"https:{tag.find('img', id='wob_tci')['src']}")
                embed.add_field(
                    name=tag.find("div", class_="vk_gy vk_h").text,
                    value=f"{tag.find('div', id='wob_dts').text}\n{tag.find('div', id='wob_dcp').text}",
                    inline=False
                )
                embed.add_field(name="Temperature", value=f"{tag.find('span', id='wob_tm').text}°C | {tag.find('span', id='wob_ttm').text}°F")
                embed.add_field(name="Precipitation", value=tag.find('span', id='wob_pp').text)
                embed.add_field(name="Humidity", value=tag.find('span', id='wob_hm').text)
                embed.add_field(name="Wind", value=tag.find('span', id='wob_ws').text)
                embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[1:5])), inline=False)
                return embed
            except:
                pass

        #simple wiki
        tag = soup.find(lambda x: x.name=="div" and x.get("class")==["mod"] and x.get("style")=="clear:none")
        if tag:
            try:
                embed = discord.Embed(title="Search result:", description=f"{tag.text}\n[{search_results[0].h3.text}]({search_results[0]['href']})", colour=discord.Colour.dark_orange())
                embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[1:5])), inline=False)
                return embed
            except:
                pass

        #translate
        tag = soup.find("div", id="tw-container")
        if tag:
            try:
                s = tag.find("div", id="tw-source")
                inp = s.find("textarea", id="tw-source-text-ta")
                inp_lang = s.find("div", class_="tw-lang-selector-wrapper").find("option", selected="1")
                t = tag.find("div", id="tw-target")
                out = t.find("pre", id="tw-target-text")
                out_lang = t.find("div", class_="tw-lang-selector-wrapper").find("option", selected="1")
                link = tag.next_sibling.find("a")
                embed = discord.Embed(title="Search result:", description=f"[Google Translate]({link['href']})", colour=discord.Colour.dark_orange())
                embed.add_field(name=inp_lang.text, value=inp.text)
                embed.add_field(name=out_lang.text, value=out.text)
                embed.add_field(name="See also:", value="\n\n".join((f"[{discord_escape(t[0])}]({safe_url(t[1])})" for t in search_results[0:4])), inline=False)
                return embed
            except:
                pass

        #non-special search
        if not search_results:
            return None

        other = "\n\n".join((f"<{r[1]}>" for r in search_results[1:5]))
        return f"**Search result:**\n{search_results[0][1]}\n**See also:**\n{other}"

    @commands.command(aliases=["g"])
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    async def google(self, ctx, *, query):
        """
        preforms a google search.
        """
        params = {
            "hl": "en",
            "q": query
        }

        await ctx.trigger_typing()
        async with self.google_lock:
            bytes_ = await fetch(self.google_session, "https://www.google.com/search", headers=self.google_headers, params=params, timeout=10)
            result = self._parse_google(bytes_.decode("utf-8"))
            if isinstance(result, discord.Embed):
                await ctx.send(embed=result)
            elif isinstance(result, str):
                await ctx.send(result)
            elif isinstance(result, list):
                paging = Pages(ctx, entries=result)
                await paging.paginate()
            else:
                await ctx.send("No result found.\nEither query yields nothing or Google blocked me")

    @google.error
    async def google_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("Hold it! you can only Google once every 10 seconds!")

    @commands.command(aliases=["translate", "trans"])
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    async def gtrans(self, ctx, *, query):
        """
        translates text from a language to english
        """
        await ctx.trigger_typing()
        params = {
            "tl": "en",
            "hl": "en",
            "sl": "auto",
            "ie": "UTF-8",
            "q": query
        }
        if not ctx.channel.is_nsfw():
            params["safe"] = "active"
        bytes_ = await fetch(self.bot.session, "http://translate.google.com/m", headers=self.google_headers, params=params, timeout=10)
        data = BS(bytes_.decode("utf-8"), "lxml")
        tag = data.find("div", class_="t0")
        lang = data.find_all("a", class_="s1")
        lang = lang[1].get_text()
        embed = discord.Embed(colour=discord.Colour.orange())
        embed.add_field(name=f"Input: {lang}", value=query)
        embed.add_field(name="English", value=tag.get_text())
        await ctx.send(embed=embed)

    @gtrans.error
    async def gtrans_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("hold it! You can only Google Translate once every 10 seconds!")

def setup(bot):
    bot.add_cog(_fun(bot))
