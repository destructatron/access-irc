"""
Message Filter Plugin for Access IRC

This plugin demonstrates how to filter incoming and outgoing messages.
It can block messages from specific users, filter out unwanted words,
or modify message content.

To use: Copy this file to ~/.config/access-irc/plugins/
"""

from access_irc.plugin_specs import hookimpl


class Plugin:
    """Message filter plugin"""

    def __init__(self):
        # Users to ignore (messages from these users will be blocked)
        self.ignored_users = set()

        # Words to filter out (will be replaced with asterisks)
        self.filtered_words = []

        # Channels to mute (all messages blocked)
        self.muted_channels = set()

    @hookimpl
    def on_startup(self, ctx):
        """Called when Access IRC starts"""
        # You could load settings from a file here
        ctx.add_system_message(
            ctx.get_current_server() or "",
            ctx.get_current_server() or "",
            "Message filter plugin loaded. Use /filter commands to configure."
        )

    @hookimpl
    def filter_incoming_message(self, ctx, server, target, sender, message):
        """Filter incoming messages.

        Returns:
            None: Allow message unchanged
            {'block': True}: Block the message entirely
            {'message': 'new text'}: Modify the message
        """
        # Block messages from ignored users
        if sender.lower() in self.ignored_users:
            return {'block': True}

        # Block messages from muted channels
        if target.lower() in self.muted_channels:
            return {'block': True}

        # Filter out specific words
        modified = message
        for word in self.filtered_words:
            if word.lower() in modified.lower():
                # Replace word with asterisks (case-insensitive)
                import re
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                modified = pattern.sub('*' * len(word), modified)

        if modified != message:
            return {'message': modified}

        return None  # Allow unchanged

    @hookimpl
    def filter_incoming_action(self, ctx, server, target, sender, action):
        """Filter incoming /me actions"""
        # Apply same rules as messages
        if sender.lower() in self.ignored_users:
            return {'block': True}

        if target.lower() in self.muted_channels:
            return {'block': True}

        return None

    @hookimpl
    def on_command(self, ctx, server, target, command, args):
        """Handle custom /filter commands"""
        if command != "filter":
            return False

        parts = args.split(None, 1) if args else []
        subcommand = parts[0].lower() if parts else "help"
        subargs = parts[1] if len(parts) > 1 else ""

        if subcommand == "ignore":
            if subargs:
                self.ignored_users.add(subargs.lower())
                ctx.add_system_message(server, target,
                    f"Now ignoring messages from: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter ignore <nickname>")

        elif subcommand == "unignore":
            if subargs:
                self.ignored_users.discard(subargs.lower())
                ctx.add_system_message(server, target,
                    f"No longer ignoring: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter unignore <nickname>")

        elif subcommand == "list":
            if self.ignored_users:
                ctx.add_system_message(server, target,
                    f"Ignored users: {', '.join(sorted(self.ignored_users))}")
            else:
                ctx.add_system_message(server, target, "No users ignored")

            if self.filtered_words:
                ctx.add_system_message(server, target,
                    f"Filtered words: {', '.join(self.filtered_words)}")
            else:
                ctx.add_system_message(server, target, "No words filtered")

            if self.muted_channels:
                ctx.add_system_message(server, target,
                    f"Muted channels: {', '.join(sorted(self.muted_channels))}")
            else:
                ctx.add_system_message(server, target, "No channels muted")

        elif subcommand == "word":
            if subargs:
                self.filtered_words.append(subargs)
                ctx.add_system_message(server, target,
                    f"Now filtering word: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter word <word>")

        elif subcommand == "unword":
            if subargs and subargs in self.filtered_words:
                self.filtered_words.remove(subargs)
                ctx.add_system_message(server, target,
                    f"No longer filtering word: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter unword <word>")

        elif subcommand == "mute":
            if subargs:
                self.muted_channels.add(subargs.lower())
                ctx.add_system_message(server, target,
                    f"Muted channel: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter mute <#channel>")

        elif subcommand == "unmute":
            if subargs:
                self.muted_channels.discard(subargs.lower())
                ctx.add_system_message(server, target,
                    f"Unmuted channel: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /filter unmute <#channel>")

        else:
            ctx.add_system_message(server, target,
                "Filter commands: /filter ignore|unignore|word|unword|mute|unmute|list")

        return True  # Command was handled
