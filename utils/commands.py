import inspect

from discord.ext import commands
from discord.ext.commands import *
from discord import *
from .checks import *
from .context import Contexter as Context

__all__ = ["Command", "Group", "Cog", "help_check", "command", "group", "Category", "Bot"]


class Command(commands.Command):
    def __init__(self, func, *args, **kwargs):
        try:
            checks = func.__help_checks__
            checks.reverse()
        except AttributeError:
            checks = kwargs.get('help_checks', [])
        finally:
            self._help_checks = checks
        super().__init__(func, **kwargs)
    
    def help_check(self, coro):
        self._help_checks.append(coro)
    
    async def run_help_checks(self, ctx):
        allowed = True
        for check in self._help_checks:
            try:
                if not await check(ctx):
                    allowed = False
            except commands.CommandError:
                raise
            except Exception as e:
                pass # something happened, ignore it
        return allowed


class Group(commands.Group):
    def __init__(self, func, *args, **kwargs):
        try:
            checks = func.__help_checks__
            checks.reverse()
        except AttributeError:
            checks = kwargs.get('help_checks', [])
        finally:
            self._help_checks = checks
        self.walk_help = kwargs.get("walk_help", True)
        super().__init__(func, *args, **kwargs)
    
    def help_check(self, coro):
        self._help_checks.append(coro)

    async def run_help_checks(self, ctx):
        allowed = True
        for check in self._help_checks:
            try:
                if not await check(ctx):
                    allowed = False
            except commands.CommandError:
                raise
            except Exception as e:
                pass # something happened, ignore it
        return allowed


class Cog(commands.Cog):
    walk_on_help = False
    category = None
    _category = None
    hidden = False
    def name(self):
        return self.qualified_name

    def _inject(self, bot):
        super()._inject(bot)
        if self.category is not None:
            self._category = bot.assign_category(self.category, self)
        return self

    def _eject(self, bot):
        super()._eject(bot)
        if self._category is not None:
            self._category.remove_cog(self)


class Category:
    description = ""
    help = ""
    brief = ""
    title = ""
    walk_on_help = False

    def __init__(self, name, description=None, help=None, brief=None, title=None):
        self.name = name
        self.title = title or name
        self.description = description or self.description
        self.help = help or self.help
        self.brief = brief or self.brief
        self.cogs = {}

    def get_cogs(self):
        return set(self.cogs.values())

    @property
    def commands(self):
        ret = []
        for c in self.cogs.values():
            for com in c.get_commands():
                ret.append(com)
        return ret

    def walk_commands(self):
        for c in self.cogs.values():
            yield from c.walk_commands()

    def assign_cog(self, cog):
        self.cogs[cog.qualified_name] = cog
        if not self.walk_on_help and hasattr(cog, "walk_on_help"):
            self.walk_on_help = cog.walk_on_help
        if hasattr(cog, "cat_description"):
            help_doc = inspect.cleandoc(cog.cat_description)
            self.description = help_doc

        if not self.description:
            help_doc = inspect.getdoc(cog)
            if isinstance(help_doc, bytes):
                help_doc = help_doc.decode('utf-8')

            self.description = help_doc
            self.brief = self.description

    def remove_cog(self, cog):
        del self.cogs[cog.qualified_name]

def command(name=None, **optns):
    return commands.command(name, cls=Command, **optns)

def group(name=None, **optns):
    return commands.group(name, cls=Group, **optns)

def help_check(predicate):
    def decorator(func):
        if isinstance(func, Command):
            func._help_checks.append(predicate)
        else:
            if not hasattr(func, '__help_checks__'):
                func.__help_checks__ = []

            func.__help_checks__.append(predicate)

        return func
    return decorator

def cooler():
    return cooldown(3, 5, BucketType.user)