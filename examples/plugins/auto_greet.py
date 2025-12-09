"""
Auto Greet Plugin for Access IRC

This plugin automatically greets users when they join channels.
It demonstrates the on_join hook and timer functionality.

To use: Copy this file to ~/.config/access-irc/plugins/
"""

from access_irc.plugin_specs import hookimpl


class Plugin:
    """Auto-greet plugin"""

    def __init__(self):
        # Channels where auto-greet is enabled
        self.enabled_channels = set()

        # Greet message (can include {nick} placeholder)
        self.greet_message = "Welcome to the channel, {nick}!"

        # Track recent joins to avoid greeting ourselves or spam
        self.recent_joins = {}  # channel -> set of nicks

    @hookimpl
    def on_startup(self, ctx):
        """Called when Access IRC starts"""
        ctx.add_system_message(
            ctx.get_current_server() or "",
            ctx.get_current_server() or "",
            "Auto-greet plugin loaded. Use /greet enable <#channel> to enable."
        )

    @hookimpl
    def on_join(self, ctx, server, channel, nick):
        """Called when a user joins a channel"""
        # Check if greet is enabled for this channel
        if channel.lower() not in self.enabled_channels:
            return

        # Don't greet ourselves
        our_nick = ctx.get_nickname(server)
        if our_nick and nick.lower() == our_nick.lower():
            return

        # Send greeting (with a small delay to be polite)
        message = self.greet_message.format(nick=nick)

        def send_greeting():
            ctx.send_message(server, channel, message)

        # Delay greeting by 2 seconds
        ctx.add_timeout(2000, send_greeting)

    @hookimpl
    def on_command(self, ctx, server, target, command, args):
        """Handle /greet commands"""
        if command != "greet":
            return False

        parts = args.split(None, 1) if args else []
        subcommand = parts[0].lower() if parts else "help"
        subargs = parts[1] if len(parts) > 1 else ""

        if subcommand == "enable":
            channel = subargs or target
            if channel.startswith("#"):
                self.enabled_channels.add(channel.lower())
                ctx.add_system_message(server, target,
                    f"Auto-greet enabled for {channel}")
            else:
                ctx.add_system_message(server, target,
                    "Usage: /greet enable <#channel>")

        elif subcommand == "disable":
            channel = subargs or target
            self.enabled_channels.discard(channel.lower())
            ctx.add_system_message(server, target,
                f"Auto-greet disabled for {channel}")

        elif subcommand == "message":
            if subargs:
                self.greet_message = subargs
                ctx.add_system_message(server, target,
                    f"Greet message set to: {subargs}")
            else:
                ctx.add_system_message(server, target,
                    f"Current message: {self.greet_message}")
                ctx.add_system_message(server, target,
                    "Use {nick} as placeholder for the user's nickname")

        elif subcommand == "list":
            if self.enabled_channels:
                ctx.add_system_message(server, target,
                    f"Enabled channels: {', '.join(sorted(self.enabled_channels))}")
            else:
                ctx.add_system_message(server, target,
                    "No channels have auto-greet enabled")

        else:
            ctx.add_system_message(server, target,
                "Greet commands: /greet enable|disable|message|list")

        return True
