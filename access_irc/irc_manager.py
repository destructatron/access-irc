#!/usr/bin/env python3
"""
IRC Manager for Access IRC
Handles multiple IRC server connections using miniirc
"""

import threading
from datetime import datetime
from typing import Dict, Callable, Optional, List, Any
from gi.repository import GLib

try:
    import miniirc
    MINIIRC_AVAILABLE = True
except ImportError:
    MINIIRC_AVAILABLE = False
    print("Warning: miniirc not available. Please install with: pip install miniirc")


class IRCConnection:
    """Represents a single IRC server connection"""

    def __init__(self, server_config: Dict[str, Any], callbacks: Dict[str, Callable]):
        """
        Initialize IRC connection

        Args:
            server_config: Server configuration dict
            callbacks: Dict of callback functions (on_message, on_join, on_part, on_connect, on_disconnect)
        """
        self.server_name = server_config.get("name", "Unknown")
        self.host = server_config.get("host")
        self.port = server_config.get("port", 6667)
        self.ssl = server_config.get("ssl", False)
        self.verify_ssl = server_config.get("verify_ssl", True)
        self.channels = server_config.get("channels", [])
        self.nickname = server_config.get("nickname", "IRCUser")
        self.realname = server_config.get("realname", "Access IRC User")

        # Authentication
        self.username = server_config.get("username", "")
        self.password = server_config.get("password", "")
        self.use_sasl = server_config.get("sasl", False)

        self.callbacks = callbacks
        self.irc: Optional[miniirc.IRC] = None
        self.connected = False
        self.current_channels: List[str] = []

        # Track users in each channel: Dict[channel, Set[nickname]]
        self.channel_users: Dict[str, set] = {}

    def _call_callback(self, callback_name: str, *args) -> bool:
        """
        Helper to call a callback and ensure it returns False for GLib.idle_add

        Args:
            callback_name: Name of callback in self.callbacks dict
            *args: Arguments to pass to callback

        Returns:
            False (to prevent callback from being called again)
        """
        callback = self.callbacks.get(callback_name)
        if callback:
            callback(*args)
        return False

    def connect(self) -> bool:
        """
        Connect to IRC server

        Returns:
            True if connection initiated successfully
        """
        if not MINIIRC_AVAILABLE:
            print("miniirc not available")
            return False

        try:
            # Prepare authentication based on SASL setting
            server_password = None
            ns_identity = None

            if self.username and self.password:
                if self.use_sasl:
                    # SASL authentication (NickServ)
                    # miniirc expects a tuple: (username, password)
                    ns_identity = (self.username, self.password)
                else:
                    # Bouncer authentication (ZNC style: username:password)
                    server_password = f"{self.username}:{self.password}"

            # Create IRC instance
            self.irc = miniirc.IRC(
                ip=self.host,
                port=self.port,
                nick=self.nickname,
                channels=self.channels,
                ssl=self.ssl,
                verify_ssl=self.verify_ssl,
                ident=self.username if self.username else self.nickname,
                realname=self.realname,
                auto_connect=False,
                ping_interval=60,
                persist=True,
                server_password=server_password,
                ns_identity=ns_identity
            )

            # Register handlers
            self._register_handlers()

            # Start connection in separate thread
            self.irc.connect()

            return True

        except Exception as e:
            print(f"Failed to connect to {self.server_name}: {e}")
            return False

    def _register_handlers(self) -> None:
        """Register IRC event handlers"""

        def on_connect(irc, hostmask, args):
            """Handle successful connection"""
            self.connected = True
            GLib.idle_add(self._call_callback, "on_connect", self.server_name)

        def on_message(irc, hostmask, args):
            """Handle incoming messages"""
            # hostmask format: nick!user@host
            sender = hostmask[0] if hostmask else "Unknown"
            target = args[0]  # Channel or nick
            message = args[-1]

            # Check if it's a private message or channel message
            is_private = target == self.nickname
            # For PMs, use the sender's nickname as the target so we can track conversations
            channel = sender if is_private else target

            # Check for CTCP ACTION (/me)
            if message.startswith('\x01ACTION ') and message.endswith('\x01'):
                # Extract action text
                action = message[8:-1]  # Remove \x01ACTION and trailing \x01
                # Call on_action callback
                GLib.idle_add(
                    self._call_callback,
                    "on_action",
                    self.server_name,
                    channel,
                    sender,
                    action,
                    is_private
                )
            else:
                # Regular message
                # Check if nickname is mentioned
                is_mention = self.nickname.lower() in message.lower()

                # Use GLib.idle_add to call callback in GTK main thread
                GLib.idle_add(
                    self._call_callback,
                    "on_message",
                    self.server_name,
                    channel,
                    sender,
                    message,
                    is_mention,
                    is_private
                )

        def on_join(irc, hostmask, args):
            """Handle user join"""
            nick = hostmask[0] if hostmask else "Unknown"
            channel = args[0]

            # Track our own channel joins
            if nick == self.nickname and channel not in self.current_channels:
                self.current_channels.append(channel)

            # Add user to channel user list
            self.add_user_to_channel(channel, nick)

            GLib.idle_add(
                self._call_callback,
                "on_join",
                self.server_name,
                channel,
                nick
            )

        def on_part(irc, hostmask, args):
            """Handle user part"""
            nick = hostmask[0] if hostmask else "Unknown"
            channel = args[0]
            reason = args[1] if len(args) > 1 else ""

            # Track our own channel parts
            if nick == self.nickname and channel in self.current_channels:
                self.current_channels.remove(channel)
                # Clear the entire user list for this channel when we leave
                self.clear_channel_users(channel)
            else:
                # Remove user from channel user list
                self.remove_user_from_channel(channel, nick)

            GLib.idle_add(
                self._call_callback,
                "on_part",
                self.server_name,
                channel,
                nick,
                reason
            )

        def on_quit(irc, hostmask, args):
            """Handle user quit"""
            nick = hostmask[0] if hostmask else "Unknown"
            reason = args[0] if args else ""

            # Capture which channels the user was in BEFORE removing them
            affected_channels = []
            for channel in self.channel_users:
                if nick in self.channel_users[channel]:
                    affected_channels.append(channel)

            # Remove user from all channels
            self.remove_user_from_all_channels(nick)

            GLib.idle_add(
                self._call_callback,
                "on_quit",
                self.server_name,
                nick,
                reason,
                affected_channels
            )

        def on_nick(irc, hostmask, args):
            """Handle nick change"""
            old_nick = hostmask[0] if hostmask else "Unknown"
            new_nick = args[0]

            # Track our own nick changes
            if old_nick == self.nickname:
                self.nickname = new_nick

            # Rename user in all channels
            self.rename_user(old_nick, new_nick)

            GLib.idle_add(
                self._call_callback,
                "on_nick",
                self.server_name,
                old_nick,
                new_nick
            )

        def on_names_reply(irc, hostmask, args):
            """Handle NAMES reply (353)"""
            # args format: [nickname, channel_type, channel, names_list]
            # Example: ['yournick', '=', '#channel', 'user1 user2 @user3 +user4']
            if len(args) >= 4:
                channel = args[2]
                names_str = args[3]

                # Parse names and keep mode prefixes (@, +, %, ~, &) to show permissions
                for name in names_str.split():
                    self.add_user_to_channel(channel, name)

                users = self.get_channel_users(channel)

                # Notify GUI of user list update
                GLib.idle_add(
                    self._call_callback,
                    "on_names",
                    self.server_name,
                    channel,
                    users
                )

        def on_kick(irc, hostmask, args):
            """Handle user kick"""
            # args format: [channel, kicked_nick, reason]
            kicker = hostmask[0] if hostmask else "Unknown"
            channel = args[0]
            kicked_nick = args[1]
            reason = args[2] if len(args) > 2 else ""

            # Remove kicked user from channel
            self.remove_user_from_channel(channel, kicked_nick)

            # If we were kicked, clear the channel
            if kicked_nick == self.nickname and channel in self.current_channels:
                self.current_channels.remove(channel)
                self.clear_channel_users(channel)

            GLib.idle_add(
                self._call_callback,
                "on_kick",
                self.server_name,
                channel,
                kicker,
                kicked_nick,
                reason
            )

        def on_endofnames(irc, hostmask, args):
            """Handle end of NAMES list (366) - indicates we're in a channel"""
            # args format: [nickname, channel, "End of /NAMES list"]
            if len(args) >= 2:
                channel = args[1]
                # Check if this channel is already in our list
                if channel not in self.current_channels:
                    self.current_channels.append(channel)
                    # Trigger a join event to add to tree
                    GLib.idle_add(
                        self._call_callback,
                        "on_join",
                        self.server_name,
                        channel,
                        self.nickname
                    )

        def on_notice(irc, hostmask, args):
            """Handle NOTICE messages"""
            # hostmask format: nick!user@host or server name
            sender = hostmask[0] if hostmask else "Server"
            target = args[0]  # Channel or nick
            message = args[-1]

            # Check if it's a private notice or channel notice
            is_private = target == self.nickname
            # For private notices, use the sender's nickname as the target
            channel = sender if is_private else target

            # Use GLib.idle_add to call callback in GTK main thread
            GLib.idle_add(
                self._call_callback,
                "on_notice",
                self.server_name,
                channel,
                sender,
                message
            )

        def on_whois_user(irc, hostmask, args):
            """Handle WHOIS user reply (311)"""
            # args format: [our_nick, target_nick, username, host, *, realname]
            if len(args) >= 6:
                nick = args[1]
                username = args[2]
                host = args[3]
                realname = args[5]
                message = f"WHOIS {nick}: {realname} ({username}@{host})"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_server(irc, hostmask, args):
            """Handle WHOIS server reply (312)"""
            # args format: [our_nick, target_nick, server, server_info]
            if len(args) >= 4:
                nick = args[1]
                server = args[2]
                server_info = args[3]
                message = f"WHOIS {nick}: connected to {server} ({server_info})"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_operator(irc, hostmask, args):
            """Handle WHOIS operator reply (313)"""
            # args format: [our_nick, target_nick, :is an IRC operator]
            if len(args) >= 2:
                nick = args[1]
                message = f"WHOIS {nick}: is an IRC operator"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_idle(irc, hostmask, args):
            """Handle WHOIS idle reply (317)"""
            # args format: [our_nick, target_nick, idle_seconds, signon_time, :message]
            if len(args) >= 3:
                nick = args[1]
                idle_seconds = int(args[2])
                idle_minutes = idle_seconds // 60
                idle_hours = idle_minutes // 60
                idle_days = idle_hours // 24

                if idle_days > 0:
                    idle_str = f"{idle_days}d {idle_hours % 24}h"
                elif idle_hours > 0:
                    idle_str = f"{idle_hours}h {idle_minutes % 60}m"
                elif idle_minutes > 0:
                    idle_str = f"{idle_minutes}m"
                else:
                    idle_str = f"{idle_seconds}s"

                message = f"WHOIS {nick}: idle {idle_str}"
                if len(args) >= 4:
                    # Add signon time if available
                    signon_timestamp = int(args[3])
                    signon_date = datetime.fromtimestamp(signon_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    message += f", signed on at {signon_date}"

                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_channels(irc, hostmask, args):
            """Handle WHOIS channels reply (319)"""
            # args format: [our_nick, target_nick, :channels list]
            if len(args) >= 3:
                nick = args[1]
                channels = args[2]
                message = f"WHOIS {nick}: in channels {channels}"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_account(irc, hostmask, args):
            """Handle WHOIS account reply (330)"""
            # args format: [our_nick, target_nick, account, :is logged in as]
            if len(args) >= 3:
                nick = args[1]
                account = args[2]
                message = f"WHOIS {nick}: logged in as {account}"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_whois_secure(irc, hostmask, args):
            """Handle WHOIS secure connection reply (671)"""
            # args format: [our_nick, target_nick, :is using a secure connection]
            if len(args) >= 2:
                nick = args[1]
                message = f"WHOIS {nick}: using a secure connection (SSL/TLS)"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_end_of_whois(irc, hostmask, args):
            """Handle end of WHOIS reply (318)"""
            # args format: [our_nick, target_nick, :End of /WHOIS list]
            if len(args) >= 2:
                nick = args[1]
                message = f"End of WHOIS for {nick}"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        # Register handlers with IRC instance
        self.irc.Handler("001", colon=False)(on_connect)  # RPL_WELCOME
        self.irc.Handler("PRIVMSG", colon=False)(on_message)
        self.irc.Handler("NOTICE", colon=False)(on_notice)
        self.irc.Handler("JOIN", colon=False)(on_join)
        self.irc.Handler("PART", colon=False)(on_part)
        self.irc.Handler("QUIT", colon=False)(on_quit)
        self.irc.Handler("NICK", colon=False)(on_nick)
        self.irc.Handler("353", colon=False)(on_names_reply)  # RPL_NAMREPLY
        self.irc.Handler("366", colon=False)(on_endofnames)  # RPL_ENDOFNAMES
        self.irc.Handler("KICK", colon=False)(on_kick)

        # WHOIS reply handlers
        self.irc.Handler("311", colon=False)(on_whois_user)  # RPL_WHOISUSER
        self.irc.Handler("312", colon=False)(on_whois_server)  # RPL_WHOISSERVER
        self.irc.Handler("313", colon=False)(on_whois_operator)  # RPL_WHOISOPERATOR
        self.irc.Handler("317", colon=False)(on_whois_idle)  # RPL_WHOISIDLE
        self.irc.Handler("318", colon=False)(on_end_of_whois)  # RPL_ENDOFWHOIS
        self.irc.Handler("319", colon=False)(on_whois_channels)  # RPL_WHOISCHANNELS
        self.irc.Handler("330", colon=False)(on_whois_account)  # RPL_WHOISACCOUNT
        self.irc.Handler("671", colon=False)(on_whois_secure)  # RPL_WHOISSECURE

    def send_message(self, target: str, message: str) -> None:
        """
        Send message to channel or user

        Args:
            target: Channel name or nick
            message: Message to send
        """
        if self.irc and self.connected:
            try:
                self.irc.msg(target, message)
            except Exception as e:
                print(f"Failed to send message to {target}: {e}")

    def send_action(self, target: str, action: str) -> None:
        """
        Send CTCP ACTION message (/me)

        Args:
            target: Channel name or nick
            action: Action text
        """
        if self.irc and self.connected:
            try:
                # CTCP ACTION format: \x01ACTION text\x01
                self.irc.msg(target, f"\x01ACTION {action}\x01")
            except Exception as e:
                print(f"Failed to send action to {target}: {e}")

    def join_channel(self, channel: str) -> None:
        """
        Join a channel

        Args:
            channel: Channel name (with or without #)
        """
        if self.irc and self.connected:
            if not channel.startswith("#"):
                channel = "#" + channel
            try:
                self.irc.join(channel)
            except Exception as e:
                print(f"Failed to join {channel}: {e}")

    def part_channel(self, channel: str, reason: str = "") -> None:
        """
        Leave a channel

        Args:
            channel: Channel name
            reason: Part reason (optional)
        """
        if self.irc and self.connected:
            try:
                self.irc.part(channel, reason)
            except Exception as e:
                print(f"Failed to part {channel}: {e}")

    def disconnect(self, reason: str = "Leaving") -> None:
        """
        Disconnect from server

        Args:
            reason: Quit reason
        """
        if self.irc:
            try:
                # Send QUIT message before disconnecting
                self.irc.quote(f"QUIT :{reason}")
                self.irc.disconnect()
                self.connected = False
                GLib.idle_add(self.callbacks.get("on_disconnect"), self.server_name)
            except Exception as e:
                print(f"Error during disconnect: {e}")

    def add_user_to_channel(self, channel: str, nickname: str) -> None:
        """
        Add a user to a channel's user list

        Args:
            channel: Channel name
            nickname: User nickname
        """
        if channel not in self.channel_users:
            self.channel_users[channel] = set()
        self.channel_users[channel].add(nickname)

    def remove_user_from_channel(self, channel: str, nickname: str) -> None:
        """
        Remove a user from a channel's user list

        Args:
            channel: Channel name
            nickname: User nickname
        """
        if channel in self.channel_users:
            self.channel_users[channel].discard(nickname)

    def remove_user_from_all_channels(self, nickname: str) -> None:
        """
        Remove a user from all channels (used when they quit)

        Args:
            nickname: User nickname
        """
        for channel in self.channel_users:
            self.channel_users[channel].discard(nickname)

    def rename_user(self, old_nick: str, new_nick: str) -> None:
        """
        Rename a user across all channels

        Args:
            old_nick: Old nickname
            new_nick: New nickname
        """
        for channel in self.channel_users:
            if old_nick in self.channel_users[channel]:
                self.channel_users[channel].discard(old_nick)
                self.channel_users[channel].add(new_nick)

    def get_channel_users(self, channel: str) -> List[str]:
        """
        Get list of users in a channel

        Args:
            channel: Channel name

        Returns:
            Sorted list of usernames
        """
        if channel in self.channel_users:
            return sorted(list(self.channel_users[channel]))
        return []

    def clear_channel_users(self, channel: str) -> None:
        """
        Clear user list for a channel

        Args:
            channel: Channel name
        """
        if channel in self.channel_users:
            del self.channel_users[channel]


class IRCManager:
    """Manages multiple IRC server connections"""

    def __init__(self, config_manager, callbacks: Dict[str, Callable]):
        """
        Initialize IRC manager

        Args:
            config_manager: ConfigManager instance
            callbacks: Dict of callback functions for IRC events
        """
        self.config = config_manager
        self.callbacks = callbacks
        self.connections: Dict[str, IRCConnection] = {}

    def connect_server(self, server_config: Dict[str, Any]) -> bool:
        """
        Connect to a server

        Args:
            server_config: Server configuration dict

        Returns:
            True if connection initiated successfully
        """
        server_name = server_config.get("name", "Unknown")

        # Don't connect if already connected
        if server_name in self.connections:
            print(f"Already connected to {server_name}")
            return False

        # Add nickname from global config if not specified or empty
        if not server_config.get("nickname"):
            server_config["nickname"] = self.config.get_nickname()
        if not server_config.get("realname"):
            server_config["realname"] = self.config.get_realname()

        # Create connection
        connection = IRCConnection(server_config, self.callbacks)

        # Try to connect
        if connection.connect():
            self.connections[server_name] = connection
            return True
        else:
            return False

    def disconnect_server(self, server_name: str, reason: str = "Leaving") -> None:
        """
        Disconnect from a server

        Args:
            server_name: Name of server to disconnect from
            reason: Quit reason
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.disconnect(reason)
            del self.connections[server_name]

    def disconnect_all(self, reason: str = "Leaving") -> None:
        """
        Disconnect from all servers

        Args:
            reason: Quit reason
        """
        for server_name in list(self.connections.keys()):
            self.disconnect_server(server_name, reason)

    def send_message(self, server_name: str, target: str, message: str) -> None:
        """
        Send message to channel or user

        Args:
            server_name: Name of server
            target: Channel name or nick
            message: Message to send
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.send_message(target, message)
        else:
            print(f"Not connected to {server_name}")

    def send_action(self, server_name: str, target: str, action: str) -> None:
        """
        Send CTCP ACTION message (/me)

        Args:
            server_name: Name of server
            target: Channel name or nick
            action: Action text
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.send_action(target, action)
        else:
            print(f"Not connected to {server_name}")

    def join_channel(self, server_name: str, channel: str) -> None:
        """
        Join a channel

        Args:
            server_name: Name of server
            channel: Channel name
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.join_channel(channel)

    def part_channel(self, server_name: str, channel: str, reason: str = "") -> None:
        """
        Leave a channel

        Args:
            server_name: Name of server
            channel: Channel name
            reason: Part reason
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.part_channel(channel, reason)

    def is_connected(self, server_name: str) -> bool:
        """
        Check if connected to a server

        Args:
            server_name: Name of server

        Returns:
            True if connected
        """
        connection = self.connections.get(server_name)
        return connection.connected if connection else False

    def get_connected_servers(self) -> List[str]:
        """Get list of connected server names"""
        return [name for name, conn in self.connections.items() if conn.connected]

    def get_channels(self, server_name: str) -> List[str]:
        """
        Get list of channels for a server

        Args:
            server_name: Name of server

        Returns:
            List of channel names
        """
        connection = self.connections.get(server_name)
        return connection.current_channels if connection else []

    def get_channel_users(self, server_name: str, channel: str) -> List[str]:
        """
        Get list of users in a channel on a server

        Args:
            server_name: Name of server
            channel: Channel name

        Returns:
            Sorted list of usernames
        """
        connection = self.connections.get(server_name)
        return connection.get_channel_users(channel) if connection else []
