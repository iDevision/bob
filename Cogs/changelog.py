import inspect
changes = {
    "V1.0.0": "initial release",
    "V1.2.0": "started changelog\nrewritten database\nadded polls\nadded idea/bug command",
    "V1.2.1": "fixed issue with polls not terminating.",
    "V1.3.0": "moved to new database storage method (SQLite3)\nrevamped help command",
    "V1.3.1": "changed mute to tempmute.\nfixed tempmute not unmuting\nsquashed a lot bugs\nadded Cards Against Humanity\nadded music\nfixed the translate command\ncreated rtfm command.",
    "V1.4.0": inspect.cleandoc("""
    bug fixes to rtfm
    added the events module
    made the man behind the curtain sneakier
    regrouped some commands
    added music
    fixed automod
    fixed modlogs
    bug fixes to basically the entire bot
    """),
    "V1.4.1": "added xkcd command\ngraphs added to ping command",
    "V1.4.2": "fixed automod\nadded reactionroles",
    "V1.4.3": "- migration of large code chunks internally\n- updates to help command\n- moderation overhaul!\n- automod detects banned words case insensitively now"
    "\n- member join logs will now show if the account is new\n- added more custom command parameters/ documented them",
    "V1.4.4": "- Dev command updates\n- quick fix to the linecount command",
    "V1.4.5": "- Emergency bug fix (i hope)\n- swept up some more bad code\n- assorted bug fixes",
    "V1.4.6": "- Fixed !remove \n- other assorted bug fixes\n- added command !moddata\n- added highlight module!\n- preparations for twitch bot launch",
    "V1.4.7": "hotfix\n- fixed the annoying text at the bottom of the !ping graph",
    "V1.4.8": "hotfix\n- fixed permission error where there was no dj in the music module",
    "V1.4.9": "hotfix\n- fixed some errors due to no permissions in modlogs\n- fixed the error reporting system (long overdue)\n- fixed up some highlight problems"
    #"V1.4.10a": "- Removed qotd module\n- QOL updates to !remove\n- fixed some module states not caching properly\n- major preparations for the twitch bot launch"
}
version = "1.4.9"

most_recent = changes["V"+version]

def setup(bot):
    bot.changelog = changes
    bot.most_recent_change = most_recent
    bot.version = version