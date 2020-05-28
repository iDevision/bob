from discord.ext import commands

from . import errors

__all__ = [
    "check_moderator",
    "check_editor",
    "check_manager",
    "check_admin",
    "check_owners",
    "basic_check",
    "check_module",
    "check_guild_owner",
    "MissingRequiredRole",
    "RoleDoesNotExist",
    ]

class RoleDoesNotExist(commands.CheckFailure):
    def __init__(self, msg):
        self.message = msg
        super().__init__(msg)

class MissingRequiredRole(RoleDoesNotExist): pass


async def basic_check(ctx, mode, higher="editor"):
    if await ctx.bot.is_owner(ctx.author):
        return True
    if ctx.author.guild_permissions.administrator:
        return True
    try:
        v = ctx.bot.guild_role_states[ctx.guild.id][mode]
        role = ctx.guild.get_role(v)
        v = ctx.bot.guild_role_states[ctx.guild.id][higher]
        higherrole = ctx.guild.get_role(v)
        if not role:
            raise RoleDoesNotExist(f"The {mode} role could not be found. Are you sure you have a role set up for that?")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `{mode}` role ({role.name}) or higher to use this command")
        return True
    except (RoleDoesNotExist, MissingRequiredRole):
        raise
    except:
        raise

def check_admin():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author) or ctx.author.guild_permissions.administrator:
            return True
        raise MissingRequiredRole("You need to be a server admin to use this command!")
    return commands.check(check)

def check_guild_owner():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author) or ctx.guild.owner.id == ctx.author.id:
            return True
        raise MissingRequiredRole("You need to be the server owner to use this command!")
    return commands.check(check)

def check_owners():
    async def check(ctx):
        if ctx.author.id not in ctx.bot.owner_ids:
            raise MissingRequiredRole("You wish. this is owner only.")
    return commands.check(check)

def is_owner(user):
    return False

def check_moderator():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        role = ctx.guild.get_role(ctx.bot.guild_role_states[ctx.guild.id]['moderator'])
        higherrole = ctx.guild.get_role(ctx.bot.guild_role_states[ctx.guild.id]['editor'])
        if not role:
            raise RoleDoesNotExist(f"The Moderator role could not be found. Are you sure you have a role set up for that?")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Moderator` role ({role.name}) or higher to use this command")
        return True

    return commands.check(check)


def check_editor():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        role = ctx.bot.guild_role_states[ctx.guild.id]['moderator']
        role = ctx.guild.get_role(role)
        if not role:
            raise RoleDoesNotExist(f"The Editor role could not be found. Are you sure you have a role set up for that?")
        if role not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Bot Editor` role ({role.name}) or higher to use this command")
        return True
    return commands.check(check)


def check_manager():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        a,b = await ctx.bot.db.fetchrow("SELECT manager, editor FROM roles WHERE guild_id IS ?", ctx.guild.id)
        role = ctx.guild.get_role(a)
        higherrole = ctx.guild.get_role(b)
        if not role:
            raise RoleDoesNotExist(f"The Community Manager role could not be found. Are you sure you have a role set up for that?")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Community Manager` role ({role.name}) or higher to use this command")
        return True
    return commands.check(check)

def check_module(module: str):
    async def predicate(ctx):
        if not ctx.bot.guild_module_states[ctx.guild.id][module]:
            raise errors.ModuleDisabled(module)
        return True
    return commands.check(predicate)