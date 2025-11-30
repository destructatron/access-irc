#!/usr/bin/env python3
"""
Access IRC - An accessible IRC client for Linux
Main application entry point
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import sys
import signal

from .config_manager import ConfigManager
from .sound_manager import SoundManager
from .irc_manager import IRCManager
from .log_manager import LogManager
from .gui import AccessibleIRCWindow


class AccessIRCApplication:
    """Main application class"""

    def __init__(self):
        """Initialize application"""

        # Initialize managers
        self.config = ConfigManager()  # Uses ~/.config/access-irc/config.json by default
        self.sound = SoundManager(self.config)
        self.log = LogManager(self.config.get_log_directory())

        # Create IRC callbacks
        callbacks = {
            "on_connect": self.on_irc_connect,
            "on_disconnect": self.on_irc_disconnect,
            "on_message": self.on_irc_message,
            "on_action": self.on_irc_action,
            "on_notice": self.on_irc_notice,
            "on_join": self.on_irc_join,
            "on_part": self.on_irc_part,
            "on_quit": self.on_irc_quit,
            "on_nick": self.on_irc_nick,
            "on_names": self.on_irc_names,
            "on_kick": self.on_irc_kick,
            "on_server_message": self.on_irc_server_message
        }

        self.irc = IRCManager(self.config, callbacks)

        # Create main window
        self.window = AccessibleIRCWindow("Access IRC")
        self.window.set_managers(self.irc, self.sound, self.config, self.log)
        self.window.connect("destroy", self.on_window_destroy)

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    def run(self) -> int:
        """
        Run the application

        Returns:
            Exit code
        """
        self.window.show_all()
        self.window.update_status("Ready")

        # Auto-connect to servers after main loop starts (using idle_add to avoid race conditions)
        GLib.idle_add(self._auto_connect_servers)

        Gtk.main()
        return 0

    def _auto_connect_servers(self) -> bool:
        """
        Auto-connect to servers marked for auto-connect

        Returns:
            False to prevent GLib from repeating this callback
        """
        servers = self.config.get_servers()

        for server in servers:
            # Check if server has autoconnect enabled
            if server.get("autoconnect", False):
                server_name = server.get("name", "Unknown")

                # Attempt to connect
                if self.irc.connect_server(server):
                    # Add server to tree
                    self.window.add_server_to_tree(server_name)
                    self.window.update_status(f"Auto-connecting to {server_name}...")
                else:
                    # Show error in GUI and console
                    error_msg = f"Failed to auto-connect to {server_name}"
                    self.window.update_status(error_msg)
                    print(error_msg)

        return False  # Don't repeat this callback

    def _should_log_server(self, server_name: str) -> bool:
        """
        Check if logging is enabled for a server

        Args:
            server_name: Name of server

        Returns:
            True if logging should happen for this server
        """
        # Check if log directory is configured
        if not self.config.get_log_directory():
            return False

        # Check if server has logging enabled
        servers = self.config.get_servers()
        for server in servers:
            if server.get("name") == server_name:
                return server.get("logging_enabled", False)

        return False

    # IRC event callbacks
    def on_irc_connect(self, server_name: str) -> None:
        """Handle IRC connection established"""
        self.window.add_system_message(server_name, server_name, f"Connected to {server_name}")
        self.window.update_status(f"Connected to {server_name}")

        # Add server to tree if not already there
        # (It should already be added when connection was initiated)

    def on_irc_disconnect(self, server_name: str) -> None:
        """Handle IRC disconnection"""
        self.window.add_system_message(server_name, server_name, f"Disconnected from {server_name}")
        self.window.update_status(f"Disconnected from {server_name}")
        self.window.remove_server_from_tree(server_name)

    def on_irc_message(self, server: str, channel: str, sender: str, message: str, is_mention: bool, is_private: bool) -> None:
        """Handle incoming IRC message"""
        self.window.add_message(server, channel, sender, message, is_mention=is_mention)

        # If this is a PM (channel doesn't start with #), add it to the tree
        # Channel will be the sender's nickname for PMs
        if not channel.startswith("#"):
            self.window.add_pm_to_tree(server, channel)

        # Log message if enabled for this server
        if self._should_log_server(server):
            self.log.log_message(server, channel, sender, message)

        # Play appropriate sound
        if self.sound:
            if is_private:
                self.sound.play_privmsg()
            elif not is_mention:
                # Only play message sound if it's not a mention (mentions have their own sound)
                self.sound.play_message()

    def on_irc_action(self, server: str, channel: str, sender: str, action: str, is_mention: bool, is_private: bool) -> None:
        """Handle incoming IRC action (/me)"""
        self.window.add_action_message(server, channel, sender, action, is_mention=is_mention)

        # If this is a PM (channel doesn't start with #), add it to the tree
        if not channel.startswith("#"):
            self.window.add_pm_to_tree(server, channel)

        # Log action if enabled for this server
        if self._should_log_server(server):
            self.log.log_action(server, channel, sender, action)

        # Play appropriate sound
        if self.sound:
            if is_private:
                self.sound.play_privmsg()
            elif is_mention:
                # Play mention sound for actions that mention the user
                self.sound.play_mention()
            else:
                self.sound.play_message()

    def on_irc_notice(self, server: str, channel: str, sender: str, message: str) -> None:
        """Handle incoming IRC notice"""
        self.window.add_notice_message(server, channel, sender, message)

        # Note: Private notices are now routed to the server buffer instead of
        # opening PM windows, so we don't call add_pm_to_tree here

        # Log notice if enabled for this server
        if self._should_log_server(server):
            self.log.log_notice(server, channel, sender, message)

    def on_irc_join(self, server: str, channel: str, nick: str) -> None:
        """Handle user join"""
        message = f"{nick} has joined {channel}"
        self.window.add_system_message(server, channel, message)

        # Get the actual nickname for this server connection
        connection = self.irc.connections.get(server)
        our_nick = connection.nickname if connection else self.config.get_nickname()

        # If we joined, add channel to tree
        if nick == our_nick:
            # Find server iter and add channel
            tree_store = self.window.tree_store
            iter = tree_store.get_iter_first()
            while iter:
                server_name = tree_store.get_value(iter, 0)
                if server_name == server:
                    self.window.add_channel_to_tree(iter, channel)
                    break
                iter = tree_store.iter_next(iter)

        # Update users list if we're viewing this channel
        if self.window.current_server == server and self.window.current_target == channel:
            self.window.update_users_list()

        # Log join if enabled for this server
        if self._should_log_server(server):
            self.log.log_join(server, channel, nick)

        # Play join sound and announce if configured
        if self.sound:
            self.sound.play_join()

        if self.config.should_announce_joins_parts():
            self.window.announce_to_screen_reader(message)

    def on_irc_part(self, server: str, channel: str, nick: str, reason: str) -> None:
        """Handle user part"""
        message = f"{nick} has left {channel}"
        if reason:
            message += f" ({reason})"

        self.window.add_system_message(server, channel, message)

        # Update users list if we're viewing this channel
        if self.window.current_server == server and self.window.current_target == channel:
            self.window.update_users_list()

        # Log part if enabled for this server
        if self._should_log_server(server):
            self.log.log_part(server, channel, nick, reason)

        # Play part sound and announce if configured
        if self.sound:
            self.sound.play_part()

        if self.config.should_announce_joins_parts():
            self.window.announce_to_screen_reader(message)

    def on_irc_quit(self, server: str, nick: str, reason: str, channels: list) -> None:
        """Handle user quit"""
        message = f"{nick} has quit"
        if reason:
            message += f" ({reason})"

        # Add to all channels where this user was present
        for channel in channels:
            self.window.add_system_message(server, channel, message)

            # Log quit if enabled for this server
            if self._should_log_server(server):
                self.log.log_quit(server, channel, nick, reason)

        # Update users list if we're viewing a channel on this server
        if self.window.current_server == server and self.window.current_target:
            self.window.update_users_list()

        # Play quit sound
        if self.sound:
            self.sound.play_quit()

        # Announce if configured
        if self.config.should_announce_joins_parts():
            self.window.announce_to_screen_reader(message)

    def on_irc_nick(self, server: str, old_nick: str, new_nick: str) -> None:
        """Handle nick change"""
        message = f"{old_nick} is now known as {new_nick}"

        # Get connection to check if this is our own nick change
        connection = self.irc.connections.get(server)
        is_own_nick = False

        if connection:
            # Check if this is our own nickname changing
            # The IRC manager has already updated connection.nickname to new_nick,
            # so we check if new_nick matches the current nickname
            is_own_nick = (connection.nickname == new_nick and old_nick != new_nick)

            # If it's our own nickname, always show in server view
            if is_own_nick:
                # Show prominent message in server view
                own_message = f"Your nickname has been changed from {old_nick} to {new_nick}"
                self.window.add_system_message(server, server, own_message)
                # Announce to screen reader
                self.window.announce_to_screen_reader(own_message)

            # Add to all channels where this user is present (for own nick and others)
            for channel in connection.channel_users:
                if new_nick in connection.channel_users[channel]:
                    self.window.add_system_message(server, channel, message)

                    # Log nick change if enabled for this server
                    if self._should_log_server(server):
                        self.log.log_nick(server, channel, old_nick, new_nick)

        # Update users list if we're viewing a channel on this server
        if self.window.current_server == server and self.window.current_target:
            self.window.update_users_list()

        # Announce if configured (for other users' nick changes)
        if not is_own_nick and self.config.should_announce_joins_parts():
            self.window.announce_to_screen_reader(message)

    def on_irc_names(self, server: str, channel: str, users: list) -> None:
        """
        Handle NAMES reply (user list for channel)

        Args:
            server: Server name
            channel: Channel name
            users: List of usernames in the channel
        """
        # Update users list if we're currently viewing this channel
        if self.window.current_server == server and self.window.current_target == channel:
            self.window.update_users_list()

    def on_irc_kick(self, server: str, channel: str, kicker: str, kicked: str, reason: str) -> None:
        """
        Handle user kick

        Args:
            server: Server name
            channel: Channel name
            kicker: Username who kicked
            kicked: Username who was kicked
            reason: Kick reason
        """
        message = f"{kicked} was kicked by {kicker}"
        if reason:
            message += f" ({reason})"

        self.window.add_system_message(server, channel, message)

        # Log kick if enabled for this server
        if self._should_log_server(server):
            self.log.log_kick(server, channel, kicker, kicked, reason)

        # Update users list if we're viewing this channel
        if self.window.current_server == server and self.window.current_target == channel:
            self.window.update_users_list()

    def on_irc_server_message(self, server: str, message: str) -> None:
        """
        Handle server messages (like WHOIS replies, MOTD, etc.)

        Args:
            server: Server name
            message: Server message to display
        """
        # Display in the current view for this server
        target = self.window.current_target if self.window.current_server == server else server
        # Announce server messages to screen readers since they're important information
        self.window.add_system_message(server, target, message, announce=True)

    def on_window_destroy(self, widget) -> None:
        """Handle window destruction"""
        # Disconnect all servers with configured quit message
        quit_message = self.config.get_quit_message()
        self.irc.disconnect_all(quit_message)

        # Cleanup sound
        self.sound.cleanup()

        Gtk.main_quit()


def main():
    """Main entry point"""

    # Redirect stdout/stderr to prevent crashes when running without a terminal
    # (e.g., when run with `access-irc& disown`)
    try:
        # Try to open /dev/null for writing
        devnull = open('/dev/null', 'w')
        # Only redirect if stdout/stderr are not connected to a terminal
        # This allows debugging when run normally, but prevents crashes when backgrounded
        if not sys.stdout.isatty():
            sys.stdout = devnull
        if not sys.stderr.isatty():
            sys.stderr = devnull
    except Exception:
        # If we can't redirect, continue anyway - print statements will just fail silently
        pass

    # Check for miniirc
    try:
        import miniirc
    except ImportError:
        error_msg = "Error: miniirc is required. Install with: pip install miniirc"
        # Show dialog if no terminal, otherwise print to console
        try:
            if not sys.stdout.isatty():
                dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Missing Dependency"
                )
                dialog.format_secondary_text(error_msg)
                dialog.run()
                dialog.destroy()
            else:
                print(error_msg)
        except:
            pass  # If we can't show dialog, just exit
        return 1

    # Check for GStreamer (for sound)
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
    except (ImportError, ValueError):
        print("Warning: GStreamer is not installed. Sound notifications will be disabled.")
        print("Install with system package manager: gstreamer1.0-plugins-base gstreamer1.0-plugins-good")

    # Create and run application
    app = AccessIRCApplication()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
