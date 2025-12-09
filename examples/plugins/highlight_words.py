"""
Highlight Words Plugin for Access IRC

This plugin allows you to define additional words that trigger
screen reader announcements, beyond just your nickname.

To use: Copy this file to ~/.config/access-irc/plugins/
"""

from access_irc.plugin_specs import hookimpl


class Plugin:
    """Highlight words plugin for additional keyword notifications"""

    def __init__(self):
        # Words that trigger announcements
        self.highlight_words = set()

    @hookimpl
    def on_startup(self, ctx):
        """Called when Access IRC starts"""
        ctx.add_system_message(
            ctx.get_current_server() or "",
            ctx.get_current_server() or "",
            "Highlight plugin loaded. Use /highlight add <word> to add keywords."
        )

    @hookimpl
    def on_message(self, ctx, server, target, sender, message, is_mention):
        """Called after a message is received (post-filter)"""
        # Skip if already a mention (will be announced anyway)
        if is_mention:
            return

        # Check for highlight words
        message_lower = message.lower()
        for word in self.highlight_words:
            if word.lower() in message_lower:
                # Announce to screen reader
                ctx.announce(f"Highlight in {target}: {sender} said {message}")
                ctx.play_sound("mention")
                break

    @hookimpl
    def on_action(self, ctx, server, target, sender, action, is_mention):
        """Called after an action is received"""
        if is_mention:
            return

        action_lower = action.lower()
        for word in self.highlight_words:
            if word.lower() in action_lower:
                ctx.announce(f"Highlight in {target}: {sender} {action}")
                ctx.play_sound("mention")
                break

    @hookimpl
    def on_command(self, ctx, server, target, command, args):
        """Handle /highlight commands"""
        if command != "highlight":
            return False

        parts = args.split(None, 1) if args else []
        subcommand = parts[0].lower() if parts else "help"
        subargs = parts[1] if len(parts) > 1 else ""

        if subcommand == "add":
            if subargs:
                self.highlight_words.add(subargs.lower())
                ctx.add_system_message(server, target,
                    f"Added highlight word: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /highlight add <word>")

        elif subcommand == "remove":
            if subargs:
                self.highlight_words.discard(subargs.lower())
                ctx.add_system_message(server, target,
                    f"Removed highlight word: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /highlight remove <word>")

        elif subcommand == "list":
            if self.highlight_words:
                words = ', '.join(sorted(self.highlight_words))
                ctx.add_system_message(server, target,
                    f"Highlight words: {words}")
            else:
                ctx.add_system_message(server, target,
                    "No highlight words configured")

        elif subcommand == "clear":
            self.highlight_words.clear()
            ctx.add_system_message(server, target,
                "Cleared all highlight words")

        else:
            ctx.add_system_message(server, target,
                "Highlight commands: /highlight add|remove|list|clear")

        return True
