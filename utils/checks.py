from discord.ext import commands

from . import errors

__all__ = [
    "check_moderator",
    "check_editor",
    "check_manager",
    "check_streamer",
    "check_admin",
    "check_owners",
    "basic_check",
    "check_module",
    "MissingRequiredRole",
    "RoleDoesNotExist",
    ]

class RoleDoesNotExist(commands.CheckFailure):
    def __init__(self, msg):
        self.message = msg
        super().__init__(msg)

class MissingRequiredRole(RoleDoesNotExist): pass

all_powerful_users = [547861735391100931, 467778673995415554]


async def basic_check(ctx, mode, higher="editor"):
    if await ctx.bot.is_owner(ctx.author):
        return True
    if ctx.author.guild_permissions.administrator:
        return True
    try:
        with ctx.bot.db:
            v = ctx.bot.guild_role_states[ctx.guild.id][mode]
            role = ctx.guild.get_role(v)
            v = ctx.bot.guild_role_states[ctx.guild.id][higher]
        higherrole = ctx.guild.get_role(v)
        if not role:
            raise RoleDoesNotExist(f"the role id `{role}` does not exist in your guild. "
                                   "The role may have been deleted, or no role was ever created/assigned.")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Moderator` role ({role.name}) or higher to use this command")
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

def check_owners():
    async def check(ctx):
        if ctx.author.id not in all_powerful_users:
            raise MissingRequiredRole("You wish. this is owner only.")
    return commands.check(check)

def is_owner(user):
    return user.id in all_powerful_users

def check_moderator():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        cur = ctx.bot.db.cursor()
        cur.execute("SELECT moderator FROM roles WHERE guild_id IS ?", (ctx.guild.id,))
        v = (cur.fetchone())[0]
        role = ctx.guild.get_role(v)
        cur.execute("SELECT editor FROM roles WHERE guild_id IS ?", (ctx.guild.id,))
        higherrole = ctx.guild.get_role((cur.fetchone())[0])
        if not role:
            raise RoleDoesNotExist(f"the role id `{role}` does not exist in your guild. "
            "The role may have been deleted, or no role was ever created/assigned.")
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
        role = await ctx.bot.db.fetch("SELECT moderator FROM roles WHERE guild_id IS ?", ctx.guild.id)
        role = ctx.guild.get_role(role)
        if not role:
            raise RoleDoesNotExist(f"the role id `{role}` does not exist in your guild. "
            "The role may have been deleted, or no role was ever created/assigned.")
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
            raise RoleDoesNotExist(f"the role id `{role}` does not exist in your guild. "
            "The role may have been deleted, or no role was ever created/assigned.")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Community Manager` role ({role.name}) or higher to use this command")
        return True
    return commands.check(check)

def check_streamer():
    async def check(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        role, role2, role3 = ctx.bot.db.fetchrow("SELECT streamer, editor, manager FROM roles WHERE guild_id IS ?", ctx.guild.id)
        role = ctx.guild.get_role(role)
        higherrole = ctx.guild.get_role(role2)
        higherrole2 = ctx.guild.get_role(role3)
        if not role:
            raise RoleDoesNotExist(f"the role id `{role}` does not exist in your guild. "
            "The role may have been deleted, or no role was ever created/assigned.")
        if role not in ctx.author.roles and higherrole not in ctx.author.roles and higherrole2 not in ctx.author.roles:
            raise MissingRequiredRole(f"You need the `Streamer` role ({role.name}) or higher to use this command")
        return True
    return commands.check(check)

def check_module(module: str):
    async def predicate(ctx):
        if not ctx.bot.guild_module_states[ctx.guild.id][module]:
            raise errors.ModuleDisabled(module)
        return True
    return commands.check(predicate)