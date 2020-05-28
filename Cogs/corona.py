from utils import commands, country_codes
import difflib
import time
import coronatracker


def setup(bot):
    bot.add_cog(Corona(bot))

class Corona(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lookup = []
        self.alt_lookup = {}
        self.last_fetch = None
        self.session = None
        self.ct = coronatracker.CoronaTracker()

    @commands.command(aliases=['virus', 'coronavirus'])
    async def corona(self, ctx, *, request: str=None):
        if self.last_fetch is None or time.time() - self.last_fetch > 3600:
            self.last_fetch = time.time()
            await self.ct.aio_fetch_results()
            for country in self.ct.countries:
                self.lookup.append(country.name)
                for subcountry in country.areas:
                    self.alt_lookup[subcountry.name] = country.name

        request = request.lower().title() if request else None

        if request is None:
            return await ctx.send("Please provide a country or province")
            fmt = f"__Global Stats__\n> Total\n{self.ct.total_stats.confirmed} Confirmed Infections\n" \
                  f"{self.ct.total_stats.recovered} Recovered\n{self.ct.total_stats.deaths} Deaths"

            return await ctx.send(embed=ctx.embed_invis(description=fmt))

        try:
            country, inner = self.resolve_location(request)
        except ValueError:
            closest = await self.find_close_matches(request)
            closest = "\n".join(closest)
            emb = ctx.embed_invis(title="Not Found", description=f"Did you mean:\n{closest}")
            return await ctx.send(embed=emb)

        loc = self.ct.get_country(country)

        if inner is not None:
            loc = loc.areas[inner]

        total_deaths = loc.total_stats.deaths
        total_rec = loc.total_stats.recovered
        total_infected = loc.total_stats.confirmed


        location_name = country.title()
        if inner:
            location_name += f", {inner.title()}"

        fmt = f"__Stats for {location_name}__\n> Total\n{total_infected} Confirmed Infections\n{total_rec} Recovered\n{total_deaths} Deaths"

        emb = ctx.embed_invis(description=fmt)

        await ctx.send(embed=emb)


    def resolve_location(self, req: str):
        if req in self.lookup: # quick
            return req, None

        if req in self.alt_lookup:
            return self.alt_lookup[req], req

        if req.upper() in country_codes.alpha2:
            return country_codes.alpha2[req.upper()], None

        if req in country_codes.alt_names:
            return country_codes.alt_names[req], None

        raise ValueError

    async def find_close_matches(self, req: str)->list:
        # first, check our lookup
        first = await self.bot.loop.run_in_executor(None, difflib.get_close_matches, req, self.lookup, 3, 0.6)

        first.extend(await self.bot.loop.run_in_executor(None, difflib.get_close_matches, req, list(self.alt_lookup.keys()), 3, 0.6))

        #second, check the country codes
        poss = list(country_codes.alpha2.keys())
        poss.extend(list(country_codes.alt_names.keys()))
        second = await self.bot.loop.run_in_executor(None, difflib.get_close_matches, req.upper(), poss, 3, 0.6)

        first.extend(second)
        return list(set(first))
