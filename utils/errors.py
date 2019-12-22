from discord.ext import commands

class GoogleError(commands.CommandError): pass

class CommandInterrupt(commands.CommandError):
    def __init__(self, msg):
        self.message = msg
        Exception.__init__(self, msg)

class ModuleDisabled(commands.CommandError):
    def __init__(self, module):
        self.message = f"The {module} module is disabled!"
        super().__init__(self.message)

class BannedUser(commands.CommandError):
    def __init__(self, user):
        self.message = f"{user}, you have been banned from using BOB."
        super().__init__(self.message)