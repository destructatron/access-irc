"""
Plugin hook specifications for Access IRC

This module defines all the hooks that plugins can implement.
Plugins can hook into IRC events, commands, and application lifecycle.
"""

import pluggy

# Project name for pluggy
hookspec = pluggy.HookspecMarker("access_irc")
hookimpl = pluggy.HookimplMarker("access_irc")


class AccessIRCHookSpec:
    """Hook specifications for Access IRC plugins"""

    # =========================================================================
    # Lifecycle Hooks
    # =========================================================================

    @hookspec
    def on_startup(self, ctx):
        """Called when the application starts.

        Args:
            ctx: Plugin context object with access to application APIs
        """
        pass

    @hookspec
    def on_shutdown(self, ctx):
        """Called when the application is shutting down.

        Args:
            ctx: Plugin context object with access to application APIs
        """
        pass

    @hookspec
    def on_connect(self, ctx, server):
        """Called when connected to an IRC server.

        Args:
            ctx: Plugin context object
            server: Server name
        """
        pass

    @hookspec
    def on_disconnect(self, ctx, server):
        """Called when disconnected from an IRC server.

        Args:
            ctx: Plugin context object
            server: Server name
        """
        pass

    # =========================================================================
    # Message Filter Hooks (can modify or block messages)
    # =========================================================================

    @hookspec(firstresult=True)
    def filter_incoming_message(self, ctx, server, target, sender, message):
        """Filter incoming messages before display.

        This hook is called before a message is displayed. Plugins can:
        - Return None to allow the message through unchanged
        - Return a dict with 'message' key to modify the message text
        - Return a dict with 'block': True to block the message entirely

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or PM target
            sender: Message sender
            message: Message text

        Returns:
            None: Allow message unchanged
            dict: {'message': 'new text'} to modify, or {'block': True} to block
        """
        pass

    @hookspec(firstresult=True)
    def filter_incoming_action(self, ctx, server, target, sender, action):
        """Filter incoming CTCP ACTION (/me) messages.

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or PM target
            sender: Action sender
            action: Action text

        Returns:
            None: Allow action unchanged
            dict: {'action': 'new text'} to modify, or {'block': True} to block
        """
        pass

    @hookspec(firstresult=True)
    def filter_incoming_notice(self, ctx, server, target, sender, message):
        """Filter incoming NOTICE messages.

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or target
            sender: Notice sender
            message: Notice text

        Returns:
            None: Allow notice unchanged
            dict: {'message': 'new text'} to modify, or {'block': True} to block
        """
        pass

    @hookspec(firstresult=True)
    def filter_outgoing_message(self, ctx, server, target, message):
        """Filter outgoing messages before sending.

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or PM target
            message: Message text to send

        Returns:
            None: Allow message unchanged
            dict: {'message': 'new text'} to modify, or {'block': True} to block
        """
        pass

    # =========================================================================
    # IRC Event Hooks (notification only, cannot modify)
    # =========================================================================

    @hookspec
    def on_message(self, ctx, server, target, sender, message, is_mention):
        """Called when a message is received (after filtering).

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or PM target
            sender: Message sender
            message: Message text
            is_mention: Whether the message mentions the user
        """
        pass

    @hookspec
    def on_action(self, ctx, server, target, sender, action, is_mention):
        """Called when a CTCP ACTION (/me) is received (after filtering).

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or PM target
            sender: Action sender
            action: Action text
            is_mention: Whether the action mentions the user
        """
        pass

    @hookspec
    def on_notice(self, ctx, server, target, sender, message):
        """Called when a NOTICE is received (after filtering).

        Args:
            ctx: Plugin context object
            server: Server name
            target: Channel or target
            sender: Notice sender
            message: Notice text
        """
        pass

    @hookspec
    def on_join(self, ctx, server, channel, nick):
        """Called when a user joins a channel.

        Args:
            ctx: Plugin context object
            server: Server name
            channel: Channel name
            nick: Nick of user who joined
        """
        pass

    @hookspec
    def on_part(self, ctx, server, channel, nick, reason):
        """Called when a user leaves a channel.

        Args:
            ctx: Plugin context object
            server: Server name
            channel: Channel name
            nick: Nick of user who left
            reason: Part reason (may be empty)
        """
        pass

    @hookspec
    def on_quit(self, ctx, server, nick, reason):
        """Called when a user quits IRC.

        Args:
            ctx: Plugin context object
            server: Server name
            nick: Nick of user who quit
            reason: Quit reason
        """
        pass

    @hookspec
    def on_nick(self, ctx, server, old_nick, new_nick):
        """Called when a user changes their nick.

        Args:
            ctx: Plugin context object
            server: Server name
            old_nick: Previous nickname
            new_nick: New nickname
        """
        pass

    @hookspec
    def on_kick(self, ctx, server, channel, kicked, kicker, reason):
        """Called when a user is kicked from a channel.

        Args:
            ctx: Plugin context object
            server: Server name
            channel: Channel name
            kicked: Nick of user who was kicked
            kicker: Nick of user who kicked
            reason: Kick reason
        """
        pass

    @hookspec
    def on_topic(self, ctx, server, channel, topic, setter):
        """Called when a channel topic is changed.

        Args:
            ctx: Plugin context object
            server: Server name
            channel: Channel name
            topic: New topic text
            setter: Nick of user who set the topic (may be None)
        """
        pass

    # =========================================================================
    # Command Hooks
    # =========================================================================

    @hookspec(firstresult=True)
    def on_command(self, ctx, server, target, command, args):
        """Handle custom commands.

        Plugins can register their own /commands by implementing this hook.
        Return True if the command was handled, None/False to pass to next handler.

        Args:
            ctx: Plugin context object
            server: Current server name
            target: Current channel or PM target
            command: Command name (without leading /)
            args: Command arguments string

        Returns:
            True if command was handled, None/False otherwise
        """
        pass
