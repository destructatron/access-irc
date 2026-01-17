#!/usr/bin/env python3
"""
IRC Manager for Access IRC
Handles multiple IRC server connections using miniirc
"""

import re
import ssl
import socket
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


def strip_irc_formatting(text: str) -> str:
    """
    Strip IRC formatting codes from text

    IRC formatting codes:
    - \x03 (0x03) - Color code, followed by optional foreground (1-2 digits)
                    and optional background (comma + 1-2 digits)
    - \x02 (0x02) - Bold
    - \x1D (0x1D) - Italic
    - \x1F (0x1F) - Underline
    - \x16 (0x16) - Reverse (swap foreground/background)
    - \x0F (0x0F) - Reset all formatting

    Args:
        text: Text with IRC formatting codes

    Returns:
        Text with formatting codes removed
    """
    # Remove color codes: \x03 followed by optional foreground and background
    # Format: \x03[0-9]{1,2}(?:,[0-9]{1,2})?
    text = re.sub(r'\x03(?:\d{1,2}(?:,\d{1,2})?)?', '', text)

    # Remove other formatting codes
    text = text.replace('\x02', '')  # Bold
    text = text.replace('\x1D', '')  # Italic
    text = text.replace('\x1F', '')  # Underline
    text = text.replace('\x16', '')  # Reverse
    text = text.replace('\x0F', '')  # Reset

    return text


class IRCConnection:
    """Represents a single IRC server connection"""

    # Prefix and mode handling for user list updates
    USER_MODE_PREFIXES = {
        "q": "~",
        "a": "&",
        "o": "@",
        "h": "%",
        "v": "+",
    }
    PREFIX_RANK = {"~": 5, "&": 4, "@": 3, "%": 2, "+": 1}
    PREFIX_CHARS = set(PREFIX_RANK.keys())
    MODE_PARAMS_ALWAYS = set("beI") | set(USER_MODE_PREFIXES.keys())
    MODE_PARAMS_ON_SET = set("klfj")

    # IRC protocol limit is 512 bytes per message including CRLF
    # Reserve space for: hostmask prefix (~100), PRIVMSG command (8), target, colon-space (2), CRLF (2)
    IRC_MAX_LINE = 512
    IRC_HOSTMASK_BUFFER = 100  # Conservative estimate for :nick!user@host prefix

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
        self.base_nickname = self.nickname
        self.alternate_nicks = self._normalize_alternate_nicks(
            server_config.get("alternate_nicks", [])
        )
        self._alternate_nick_index = 0
        self.realname = server_config.get("realname", "Access IRC User")

        # Authentication
        self.username = server_config.get("username", "")
        self.password = server_config.get("password", "")
        self.use_sasl = server_config.get("sasl", False)
        self.auto_connect_commands = self._normalize_auto_commands(
            server_config.get("auto_connect_commands", [])
        )

        self.callbacks = callbacks
        self.irc: Optional[miniirc.IRC] = None
        self.connected = False
        self.current_channels: List[str] = []

        # Track users in each channel: Dict[channel, Set[nickname]]
        self.channel_users: Dict[str, set] = {}

        # Channel list storage for /list command
        self.channel_list: List[Dict[str, Any]] = []
        self.channel_list_in_progress = False

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

    def _report_server_message(self, message: str) -> None:
        """Report a server message via callback."""
        if not message:
            return
        callback = self.callbacks.get("on_server_message")
        if callback:
            GLib.idle_add(
                self._call_callback,
                "on_server_message",
                self.server_name,
                message
            )

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
            if self.alternate_nicks:
                # Disable miniirc's underscore fallback so we can use configured alternates.
                self.irc._current_nick = f"0{self.nickname}"

            # Register handlers
            self._register_handlers()

            # Start connection in separate thread
            self.irc.connect()

            return True

        except ssl.SSLCertVerificationError as e:
            error_msg = f"SSL certificate verification failed for {self.server_name}"
            hint = "If using a self-signed certificate, disable 'Verify SSL certificates' in server settings."
            print(f"{error_msg}: {e}")
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except ssl.SSLError as e:
            error_msg = f"SSL/TLS error connecting to {self.server_name}"
            hint = "Check if SSL is enabled correctly, or try disabling SSL certificate verification."
            print(f"{error_msg}: {e}")
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except socket.gaierror as e:
            error_msg = f"DNS resolution failed for {self.host}"
            hint = "Check the server hostname is correct and your internet connection is working."
            print(f"{error_msg}: {e}")
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except ConnectionRefusedError:
            error_msg = f"Connection refused by {self.host}:{self.port}"
            hint = "Check if the server is running and the port number is correct."
            print(error_msg)
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except ConnectionResetError:
            error_msg = f"Connection reset by {self.host}:{self.port}"
            hint = "The server closed the connection unexpectedly."
            print(error_msg)
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except socket.timeout:
            error_msg = f"Connection timed out to {self.host}:{self.port}"
            hint = "The server may be down or unreachable, or blocked by a firewall."
            print(error_msg)
            print(f"Hint: {hint}")
            self._report_connection_error(error_msg, hint)
            return False
        except OSError as e:
            error_msg = f"Network error connecting to {self.server_name}: {e}"
            hint = ""
            print(error_msg)
            self._report_connection_error(error_msg, hint)
            return False
        except Exception as e:
            error_msg = f"Unexpected error connecting to {self.server_name}: {type(e).__name__}: {e}"
            hint = ""
            print(error_msg)
            self._report_connection_error(error_msg, hint)
            return False

    def _report_connection_error(self, error_message: str, hint: str) -> None:
        """
        Report a connection error via callback

        Args:
            error_message: Description of the error
            hint: Helpful hint for resolving the issue
        """
        callback = self.callbacks.get("on_connection_error")
        if callback:
            GLib.idle_add(
                self._call_callback,
                "on_connection_error",
                self.server_name,
                error_message,
                hint
            )

    def _register_handlers(self) -> None:
        """Register IRC event handlers"""

        def on_connect(irc, hostmask, args):
            """Handle successful connection"""
            if args:
                self.nickname = args[0]
            self.connected = True
            self._run_auto_connect_commands()
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

            # Check for CTCP messages (start and end with \x01)
            if message.startswith('\x01') and message.endswith('\x01'):
                ctcp_content = message[1:-1]  # Remove \x01 wrappers

                # Check for DCC
                if ctcp_content.upper().startswith("DCC "):
                    # Route to DCC handler
                    GLib.idle_add(
                        self._call_callback,
                        "on_ctcp_dcc",
                        self.server_name,
                        sender,
                        ctcp_content
                    )
                    return  # Don't process as regular message

                # Check for CTCP ACTION (/me)
                if ctcp_content.startswith('ACTION '):
                    # Extract action text
                    action = ctcp_content[7:]  # Remove 'ACTION '
                    # Strip IRC formatting codes from action
                    clean_action = strip_irc_formatting(action)
                    # Check if nickname is mentioned in the action (check both original and clean)
                    is_mention = self.nickname.lower() in action.lower() or self.nickname.lower() in clean_action.lower()
                    # Call on_action callback
                    GLib.idle_add(
                        self._call_callback,
                        "on_action",
                        self.server_name,
                        channel,
                        sender,
                        clean_action,
                        is_mention,
                        is_private
                    )
                    return  # Don't process as regular message

            # Regular message (not CTCP)
            else:
                # Regular message
                # Strip IRC formatting codes from message
                clean_message = strip_irc_formatting(message)
                # Check if nickname is mentioned (check both original and clean for safety)
                is_mention = self.nickname.lower() in message.lower() or self.nickname.lower() in clean_message.lower()

                # Use GLib.idle_add to call callback in GTK main thread
                GLib.idle_add(
                    self._call_callback,
                    "on_message",
                    self.server_name,
                    channel,
                    sender,
                    clean_message,
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
                # Request topic explicitly (some bouncers don't send it on join)
                if self.irc:
                    try:
                        self.irc.quote(f"TOPIC {channel}")
                    except Exception as e:
                        print(f"Failed to request topic for {channel}: {e}")

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
                    # Request topic explicitly (useful for bouncers that don't send it on join)
                    if self.irc:
                        try:
                            self.irc.quote(f"TOPIC {channel}")
                        except Exception as e:
                            print(f"Failed to request topic for {channel}: {e}")

        def on_notice(irc, hostmask, args):
            """Handle NOTICE messages"""
            # hostmask format: nick!user@host or server name
            sender = hostmask[0] if hostmask else "Server"
            target = args[0]  # Channel or nick
            message = args[-1]

            # Check if it's a private notice or channel notice
            is_private = target == self.nickname
            # For private notices, use the server name as the target (routes to server buffer)
            # This prevents opening PM windows for every notice
            channel = self.server_name if is_private else target

            # Strip IRC formatting codes from notice message
            clean_message = strip_irc_formatting(message)

            # Use GLib.idle_add to call callback in GTK main thread
            GLib.idle_add(
                self._call_callback,
                "on_notice",
                self.server_name,
                channel,
                sender,
                clean_message
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

        def on_list_entry(irc, hostmask, args):
            """Handle channel list entry (322 RPL_LIST)"""
            # args format: [our_nick, channel, user_count, :topic]
            if len(args) >= 3:
                channel = args[1]
                try:
                    user_count = int(args[2])
                except ValueError:
                    user_count = 0
                topic = args[3] if len(args) > 3 else ""
                # Strip IRC formatting from topic
                topic = strip_irc_formatting(topic)

                self.channel_list.append({
                    "channel": channel,
                    "users": user_count,
                    "topic": topic
                })

        def on_list_end(irc, hostmask, args):
            """Handle end of channel list (323 RPL_LISTEND)"""
            self.channel_list_in_progress = False
            GLib.idle_add(
                self._call_callback,
                "on_channel_list_ready",
                self.server_name,
                self.channel_list.copy()
            )

        def on_channel_error(irc, hostmask, args):
            """Handle channel join errors (471, 473, 474, 475, 477)"""
            # args format: [our_nick, channel, :reason]
            if len(args) >= 2:
                channel = args[1]
                reason = args[2] if len(args) >= 3 else "Cannot join channel"
                message = f"Cannot join {channel}: {reason}"
                GLib.idle_add(
                    self._call_callback,
                    "on_server_message",
                    self.server_name,
                    message
                )

        def on_invite(irc, hostmask, args):
            """Handle INVITE messages"""
            # hostmask format: (nick, user, host)
            # args format: [our_nick, channel]
            if len(args) >= 2:
                inviter = hostmask[0] if hostmask else "Someone"
                channel = args[1]
                GLib.idle_add(
                    self._call_callback,
                    "on_invite",
                    self.server_name,
                    inviter,
                    channel
                )

        def on_topic_change(irc, hostmask, args):
            """Handle TOPIC changes"""
            # args format: [channel, topic]
            if len(args) >= 1:
                channel = args[0]
                topic = args[1] if len(args) >= 2 else ""
                clean_topic = strip_irc_formatting(topic)
                setter = hostmask[0] if hostmask else "Server"
                GLib.idle_add(
                    self._call_callback,
                    "on_topic_change",
                    self.server_name,
                    channel,
                    clean_topic,
                    setter
                )

        def on_topic_reply(irc, hostmask, args):
            """Handle current topic reply (332)"""
            # args format: [our_nick, channel, topic]
            if len(args) >= 3:
                channel = args[1]
                topic = args[2]
                clean_topic = strip_irc_formatting(topic)
                GLib.idle_add(
                    self._call_callback,
                    "on_topic_reply",
                    self.server_name,
                    channel,
                    clean_topic
                )

        def on_no_topic(irc, hostmask, args):
            """Handle no-topic reply (331)"""
            # args format: [our_nick, channel, :No topic is set]
            if len(args) >= 2:
                channel = args[1]
                GLib.idle_add(
                    self._call_callback,
                    "on_no_topic",
                    self.server_name,
                    channel
                )

        def on_topic_setter(irc, hostmask, args):
            """Handle topic setter reply (333)"""
            # args format: [our_nick, channel, setter, timestamp]
            if len(args) >= 4:
                channel = args[1]
                setter = args[2]
                timestamp = args[3]
                GLib.idle_add(
                    self._call_callback,
                    "on_topic_setter",
                    self.server_name,
                    channel,
                    setter,
                    timestamp
                )

        def on_mode_change(irc, hostmask, args):
            """Handle MODE changes"""
            # args format: [target, modes, params...]
            if len(args) >= 2:
                target = args[0]
                mode_str = args[1]
                params = args[2:]
                modes = " ".join(args[1:])
                setter = hostmask[0] if hostmask else "Server"

                # Update user prefixes for channel modes
                if target and target[0] in ("#", "&", "!", "+"):
                    self._apply_mode_changes(target, mode_str, params)

                GLib.idle_add(
                    self._call_callback,
                    "on_mode_change",
                    self.server_name,
                    target,
                    modes,
                    setter
                )

        def on_channel_mode(irc, hostmask, args):
            """Handle channel mode reply (324)"""
            # args format: [our_nick, channel, modes, params...]
            if len(args) >= 3:
                channel = args[1]
                modes = " ".join(args[2:])
                GLib.idle_add(
                    self._call_callback,
                    "on_channel_mode",
                    self.server_name,
                    channel,
                    modes
                )

        def on_user_mode(irc, hostmask, args):
            """Handle user mode reply (221)"""
            # args format: [our_nick, modes]
            if len(args) >= 2:
                modes = " ".join(args[1:])
                GLib.idle_add(
                    self._call_callback,
                    "on_user_mode",
                    self.server_name,
                    modes
                )

        def on_motd_line(irc, hostmask, args):
            """Handle MOTD lines and related responses"""
            if len(args) >= 2:
                line = " ".join(args[1:])
            elif args:
                line = args[0]
            else:
                return
            line = strip_irc_formatting(line)
            GLib.idle_add(
                self._call_callback,
                "on_motd_line",
                self.server_name,
                line
            )

        def make_nick_error_handler(code: str):
            def handler(irc, hostmask, args):
                """Handle nickname errors (in use, unavailable, invalid)."""
                self._handle_nick_error(code, args)
            return handler

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
        self.irc.Handler("INVITE", colon=False)(on_invite)
        self.irc.Handler("TOPIC", colon=False)(on_topic_change)
        self.irc.Handler("MODE", colon=False)(on_mode_change)

        # WHOIS reply handlers
        self.irc.Handler("311", colon=False)(on_whois_user)  # RPL_WHOISUSER
        self.irc.Handler("312", colon=False)(on_whois_server)  # RPL_WHOISSERVER
        self.irc.Handler("313", colon=False)(on_whois_operator)  # RPL_WHOISOPERATOR
        self.irc.Handler("317", colon=False)(on_whois_idle)  # RPL_WHOISIDLE
        self.irc.Handler("318", colon=False)(on_end_of_whois)  # RPL_ENDOFWHOIS
        self.irc.Handler("319", colon=False)(on_whois_channels)  # RPL_WHOISCHANNELS
        self.irc.Handler("330", colon=False)(on_whois_account)  # RPL_WHOISACCOUNT
        self.irc.Handler("671", colon=False)(on_whois_secure)  # RPL_WHOISSECURE

        # Channel list handlers
        self.irc.Handler("322", colon=False)(on_list_entry)  # RPL_LIST
        self.irc.Handler("323", colon=False)(on_list_end)  # RPL_LISTEND

        # Channel error handlers
        self.irc.Handler("471", colon=False)(on_channel_error)  # ERR_CHANNELISFULL
        self.irc.Handler("473", colon=False)(on_channel_error)  # ERR_INVITEONLYCHAN
        self.irc.Handler("474", colon=False)(on_channel_error)  # ERR_BANNEDFROMCHAN
        self.irc.Handler("475", colon=False)(on_channel_error)  # ERR_BADCHANNELKEY
        self.irc.Handler("477", colon=False)(on_channel_error)  # ERR_NEEDREGGEDNICK
        self.irc.Handler("432", colon=False)(make_nick_error_handler("432"))  # ERR_ERRONEUSNICKNAME
        self.irc.Handler("433", colon=False)(make_nick_error_handler("433"))  # ERR_NICKNAMEINUSE
        self.irc.Handler("436", colon=False)(make_nick_error_handler("436"))  # ERR_NICKCOLLISION
        self.irc.Handler("437", colon=False)(make_nick_error_handler("437"))  # ERR_UNAVAILRESOURCE

        # Topic replies
        self.irc.Handler("331", colon=False)(on_no_topic)  # RPL_NOTOPIC
        self.irc.Handler("332", colon=False)(on_topic_reply)  # RPL_TOPIC
        self.irc.Handler("333", colon=False)(on_topic_setter)  # RPL_TOPICWHOTIME

        # Mode replies
        self.irc.Handler("324", colon=False)(on_channel_mode)  # RPL_CHANNELMODEIS
        self.irc.Handler("221", colon=False)(on_user_mode)  # RPL_UMODEIS

        # MOTD replies
        self.irc.Handler("375", colon=False)(on_motd_line)  # RPL_MOTDSTART
        self.irc.Handler("372", colon=False)(on_motd_line)  # RPL_MOTD
        self.irc.Handler("376", colon=False)(on_motd_line)  # RPL_ENDOFMOTD
        self.irc.Handler("422", colon=False)(on_motd_line)  # ERR_NOMOTD

    @staticmethod
    def _normalize_auto_commands(raw_commands: Any) -> List[str]:
        """
        Normalize auto-connect command configuration into a clean list.

        Args:
            raw_commands: Config value (list or string)

        Returns:
            List of non-empty command strings
        """
        if raw_commands is None:
            return []

        if isinstance(raw_commands, str):
            commands = raw_commands.splitlines()
        elif isinstance(raw_commands, list):
            commands = raw_commands
        else:
            commands = [str(raw_commands)]

        normalized = []
        for command in commands:
            if command is None:
                continue
            text = str(command).strip()
            if not text:
                continue
            normalized.append(text)

        return normalized

    def _normalize_alternate_nicks(self, raw_nicks: Any) -> List[str]:
        """Normalize alternate nickname configuration into a clean list."""
        if raw_nicks is None:
            return []

        if isinstance(raw_nicks, str):
            candidates = [part.strip() for part in raw_nicks.replace("\n", ",").split(",")]
        elif isinstance(raw_nicks, list):
            candidates = []
            for item in raw_nicks:
                if item is None:
                    continue
                if isinstance(item, str):
                    candidates.extend(
                        [part.strip() for part in item.replace("\n", ",").split(",")]
                    )
                else:
                    candidates.append(str(item).strip())
        else:
            candidates = [str(raw_nicks).strip()]

        normalized = []
        seen = set()
        base_lower = (self.base_nickname or "").lower()
        for nick in candidates:
            if not nick:
                continue
            if nick.lower() == base_lower:
                continue
            key = nick.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(nick)

        return normalized

    def _next_alternate_nick(self) -> Optional[str]:
        """Return the next alternate nick to try, if any."""
        while self._alternate_nick_index < len(self.alternate_nicks):
            candidate = self.alternate_nicks[self._alternate_nick_index]
            self._alternate_nick_index += 1
            if candidate and candidate.lower() != self.nickname.lower():
                return candidate
        return None

    def _handle_nick_error(self, code: str, args: List[str]) -> None:
        """Handle nickname errors by retrying alternate nicknames if available."""
        auto_retry = not self.connected
        if auto_retry and not self.alternate_nicks and code in ("432", "433"):
            return

        attempted_nick = args[1] if len(args) >= 2 else self.nickname
        attempted_nick = attempted_nick or self.nickname
        reason = " ".join(args[2:]).strip() if len(args) > 2 else ""

        next_nick = None
        if auto_retry:
            next_nick = self._next_alternate_nick()
            if next_nick and self.irc:
                self.nickname = next_nick
                self.irc._desired_nick = next_nick
                if self.alternate_nicks:
                    self.irc._current_nick = f"0{next_nick}"
                try:
                    self.irc.quote(f"NICK {next_nick}")
                except Exception as e:
                    print(f"Failed to set alternate nick {next_nick}: {e}")
                    next_nick = None

        message = f"Nickname {attempted_nick} is unavailable."
        if next_nick:
            message += f" Trying {next_nick}."
        else:
            if auto_retry:
                if self.alternate_nicks:
                    message += " No alternative nicknames left."
                else:
                    message += " No alternative nicknames configured."
            message += " Use /nick to choose another."
        if reason:
            message += f" Reason: {reason}"

        self._report_server_message(message)

    def _run_auto_connect_commands(self) -> None:
        """Send configured commands after a successful connection."""
        if not self.irc or not self.connected:
            return

        for command in self.auto_connect_commands:
            self._send_auto_connect_command(command)

    def _send_auto_connect_command(self, command: str) -> None:
        """Send a single auto-connect command, supporting common slash commands."""
        if not self.irc:
            return

        raw = command.strip()
        if not raw:
            return

        if not raw.startswith("/"):
            try:
                self.irc.quote(raw)
            except Exception as e:
                print(f"Failed to send auto-connect command on {self.server_name}: {e}")
            return

        parts = raw[1:].split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        try:
            if cmd in ("msg", "query"):
                msg_parts = args.split(None, 1)
                if len(msg_parts) >= 2:
                    target = msg_parts[0].lstrip("@+%~&")
                    message = msg_parts[1]
                    self.send_message(target, message)
                else:
                    print(f"Auto-connect /{cmd} missing target or message on {self.server_name}")
            elif cmd in ("raw", "quote"):
                if args:
                    self.irc.quote(args)
            elif cmd == "nick" and args:
                self.irc.quote(f"NICK {args}")
            elif cmd == "mode" and args:
                self.irc.quote(f"MODE {args}")
            elif cmd == "join" and args:
                self.irc.quote(f"JOIN {args}")
            elif cmd in ("part", "leave") and args:
                self.irc.quote(f"PART {args}")
            elif cmd == "away":
                if args:
                    self.irc.quote(f"AWAY :{args}")
                else:
                    self.irc.quote("AWAY")
            elif cmd == "whois" and args:
                self.irc.quote(f"WHOIS {args}")
            elif cmd == "invite" and args:
                invite_parts = args.split(None, 1)
                if len(invite_parts) >= 2:
                    nick = invite_parts[0].lstrip("@+%~&")
                    channel = invite_parts[1]
                    self.irc.quote(f"INVITE {nick} {channel}")
                else:
                    print(f"Auto-connect /invite missing channel on {self.server_name}")
            elif cmd == "topic" and args:
                topic_parts = args.split(None, 1)
                if len(topic_parts) >= 2:
                    channel = topic_parts[0]
                    topic = topic_parts[1]
                    self.irc.quote(f"TOPIC {channel} :{topic}")
                else:
                    print(f"Auto-connect /topic missing channel or topic on {self.server_name}")
            else:
                # Fall back to sending the raw command without the slash.
                self.irc.quote(raw[1:])
        except Exception as e:
            print(f"Failed to send auto-connect command on {self.server_name}: {e}")

    def request_channel_list(self) -> bool:
        """
        Request channel list from server

        Returns:
            True if request was sent, False if already in progress or not connected
        """
        if not self.irc or not self.connected:
            return False

        if self.channel_list_in_progress:
            return False

        self.channel_list = []
        self.channel_list_in_progress = True
        self.irc.quote("LIST")
        return True

    def _calculate_max_message_length(self, target: str, extra_overhead: int = 0) -> int:
        """
        Calculate maximum message length for a given target.

        IRC messages have a 512 byte limit including CRLF. When sending PRIVMSG,
        the format is: PRIVMSG target :message\r\n
        The server also prepends :nick!user@host when relaying.

        Args:
            target: Channel name or nick
            extra_overhead: Additional bytes to reserve (e.g., for CTCP wrapper)

        Returns:
            Maximum safe message length in bytes
        """
        # Format: PRIVMSG target :message\r\n
        # Overhead: "PRIVMSG " (8) + target + " :" (2) + "\r\n" (2) + hostmask buffer
        overhead = 8 + len(target.encode('utf-8')) + 2 + 2 + self.IRC_HOSTMASK_BUFFER + extra_overhead
        return self.IRC_MAX_LINE - overhead

    def _split_message(self, message: str, max_length: int) -> List[str]:
        """
        Split a message into chunks that fit within the IRC limit.

        Attempts to split on word boundaries when possible for readability.

        Args:
            message: Message to split
            max_length: Maximum length per chunk in bytes

        Returns:
            List of message chunks
        """
        if len(message.encode('utf-8')) <= max_length:
            return [message]

        chunks = []
        remaining = message

        while remaining:
            # Encode to check byte length
            remaining_bytes = remaining.encode('utf-8')

            if len(remaining_bytes) <= max_length:
                chunks.append(remaining)
                break

            # Find a good split point
            # Start at max_length and work backwards to find a space
            split_point = max_length

            # Decode back to find character boundary
            # This handles multi-byte UTF-8 characters properly
            chunk_bytes = remaining_bytes[:split_point]
            # Decode, potentially truncating a multi-byte character
            try:
                chunk = chunk_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # We cut in the middle of a multi-byte character, back up
                while split_point > 0:
                    split_point -= 1
                    try:
                        chunk = remaining_bytes[:split_point].decode('utf-8')
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # Couldn't decode anything, shouldn't happen
                    chunk = remaining[:max_length // 4]  # Conservative fallback

            # Try to split on a word boundary (space)
            last_space = chunk.rfind(' ')
            if last_space > max_length // 2:  # Only if space is in second half
                chunk = chunk[:last_space]

            chunks.append(chunk)
            remaining = remaining[len(chunk):].lstrip()  # Remove leading spaces from next chunk

        return chunks

    def send_message(self, target: str, message: str) -> List[str]:
        """
        Send message to channel or user, splitting if necessary.

        IRC has a 512 byte limit per message. This method automatically
        splits long messages into multiple chunks.

        Args:
            target: Channel name or nick
            message: Message to send

        Returns:
            List of message chunks that were sent
        """
        if not self.irc or not self.connected:
            return []

        max_length = self._calculate_max_message_length(target)
        chunks = self._split_message(message, max_length)

        sent_chunks = []
        for chunk in chunks:
            try:
                self.irc.msg(target, chunk)
                sent_chunks.append(chunk)
            except Exception as e:
                print(f"Failed to send message to {target}: {e}")
                break

        return sent_chunks

    def send_action(self, target: str, action: str) -> List[str]:
        """
        Send CTCP ACTION message (/me), splitting if necessary.

        IRC has a 512 byte limit per message. This method automatically
        splits long actions into multiple chunks.

        Args:
            target: Channel name or nick
            action: Action text

        Returns:
            List of action chunks that were sent
        """
        if not self.irc or not self.connected:
            return []

        # CTCP ACTION format: \x01ACTION text\x01 adds 9 bytes overhead
        ctcp_overhead = 9  # \x01ACTION \x01
        max_length = self._calculate_max_message_length(target, ctcp_overhead)
        chunks = self._split_message(action, max_length)

        sent_chunks = []
        for chunk in chunks:
            try:
                self.irc.msg(target, f"\x01ACTION {chunk}\x01")
                sent_chunks.append(chunk)
            except Exception as e:
                print(f"Failed to send action to {target}: {e}")
                break

        return sent_chunks

    def send_ctcp(self, target: str, message: str) -> None:
        """
        Send a CTCP message

        Args:
            target: Target nickname
            message: CTCP message content (without \\x01 wrappers)
        """
        if self.irc and self.connected:
            try:
                self.irc.msg(target, f"\x01{message}\x01")
            except Exception as e:
                print(f"Failed to send CTCP to {target}: {e}")

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
                self.irc.quote(f"JOIN {channel}")
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
                if reason:
                    self.irc.quote(f"PART {channel} :{reason}")
                else:
                    self.irc.quote(f"PART {channel}")
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
        # Remove any existing entry for this nick (with or without prefix)
        self._remove_user_variants(channel, nickname)
        self.channel_users[channel].add(nickname)

    def remove_user_from_channel(self, channel: str, nickname: str) -> None:
        """
        Remove a user from a channel's user list

        Args:
            channel: Channel name
            nickname: User nickname
        """
        if channel in self.channel_users:
            self._remove_user_variants(channel, nickname)

    def remove_user_from_all_channels(self, nickname: str) -> None:
        """
        Remove a user from all channels (used when they quit)

        Args:
            nickname: User nickname
        """
        for channel in self.channel_users:
            self._remove_user_variants(channel, nickname)

    def rename_user(self, old_nick: str, new_nick: str) -> None:
        """
        Rename a user across all channels

        Args:
            old_nick: Old nickname
            new_nick: New nickname
        """
        for channel in self.channel_users:
            existing = self._find_user_entry(channel, old_nick)
            if existing is None:
                continue
            prefix = self._get_prefix(existing)
            self._remove_user_variants(channel, old_nick)
            if prefix:
                self.channel_users[channel].add(f"{prefix}{new_nick}")
            else:
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

    def _strip_prefix(self, nickname: str) -> str:
        """Strip common IRC mode prefixes from a nickname."""
        if not nickname:
            return nickname
        while nickname and nickname[0] in self.PREFIX_CHARS:
            nickname = nickname[1:]
        return nickname

    def _get_prefix(self, nickname: str) -> str:
        """Return the mode prefix for a nickname, if present."""
        if nickname and nickname[0] in self.PREFIX_CHARS:
            return nickname[0]
        return ""

    def _find_user_entry(self, channel: str, nickname: str) -> Optional[str]:
        """Find a stored user entry for a nickname in a channel (with any prefix)."""
        if channel not in self.channel_users:
            return None
        base = self._strip_prefix(nickname)
        for entry in self.channel_users[channel]:
            if self._strip_prefix(entry) == base:
                return entry
        return None

    def _remove_user_variants(self, channel: str, nickname: str) -> Optional[str]:
        """Remove any stored variants of a nickname (with or without prefix)."""
        if channel not in self.channel_users:
            return None
        base = self._strip_prefix(nickname)
        removed = None
        for entry in list(self.channel_users[channel]):
            if self._strip_prefix(entry) == base:
                if removed is None:
                    removed = entry
                self.channel_users[channel].discard(entry)
        return removed

    def _pick_higher_prefix(self, current: str, new: str) -> str:
        """Pick the higher-ranked prefix between current and new."""
        if not current:
            return new
        if not new:
            return current
        return new if self.PREFIX_RANK.get(new, 0) > self.PREFIX_RANK.get(current, 0) else current

    def _update_user_prefix(self, channel: str, nickname: str, mode: str, sign: str) -> bool:
        """Update a user's displayed prefix based on mode changes."""
        if channel not in self.channel_users:
            return False

        base = self._strip_prefix(nickname)
        current_entry = self._find_user_entry(channel, base)
        if current_entry is None and sign == "-":
            return False

        current_prefix = self._get_prefix(current_entry) if current_entry else ""
        target_prefix = self.USER_MODE_PREFIXES.get(mode)
        if not target_prefix:
            return False

        if sign == "+":
            new_prefix = self._pick_higher_prefix(current_prefix, target_prefix)
        else:
            if current_prefix == target_prefix:
                new_prefix = ""
            else:
                new_prefix = current_prefix

        # Avoid needless churn
        if current_entry:
            existing_prefix = self._get_prefix(current_entry)
            if existing_prefix == new_prefix and self._strip_prefix(current_entry) == base:
                return False

        self._remove_user_variants(channel, base)
        display = f"{new_prefix}{base}" if new_prefix else base
        self.channel_users[channel].add(display)
        return True

    def _parse_mode_changes(self, mode_str: str, params: List[str]) -> List[tuple]:
        """Parse MODE changes into a list of (sign, mode, nick) for user modes."""
        changes = []
        sign = "+"
        param_index = 0

        for ch in mode_str:
            if ch in "+-":
                sign = ch
                continue

            needs_param = False
            if ch in self.MODE_PARAMS_ALWAYS:
                needs_param = True
            elif ch in self.MODE_PARAMS_ON_SET and sign == "+":
                needs_param = True

            param = None
            if needs_param:
                if param_index >= len(params):
                    break
                param = params[param_index]
                param_index += 1

            if ch in self.USER_MODE_PREFIXES and param:
                changes.append((sign, ch, param))

        return changes

    def _apply_mode_changes(self, channel: str, mode_str: str, params: List[str]) -> bool:
        """Apply user prefix updates from MODE changes."""
        changed = False
        for sign, mode, nick in self._parse_mode_changes(mode_str, params):
            if self._update_user_prefix(channel, nick, mode, sign):
                changed = True
        return changed


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
        self._connections_lock = threading.Lock()  # Protect connections dict access

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
        if "alternate_nicks" not in server_config or server_config.get("alternate_nicks") is None:
            server_config["alternate_nicks"] = self.config.get_alternate_nicks()

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

    def send_message(self, server_name: str, target: str, message: str) -> List[str]:
        """
        Send message to channel or user, splitting if necessary.

        IRC has a 512 byte limit per message. This method automatically
        splits long messages into multiple chunks.

        Args:
            server_name: Name of server
            target: Channel name or nick
            message: Message to send

        Returns:
            List of message chunks that were sent
        """
        connection = self.connections.get(server_name)
        if connection:
            return connection.send_message(target, message)
        else:
            print(f"Not connected to {server_name}")
            return []

    def send_action(self, server_name: str, target: str, action: str) -> List[str]:
        """
        Send CTCP ACTION message (/me), splitting if necessary.

        IRC has a 512 byte limit per message. This method automatically
        splits long actions into multiple chunks.

        Args:
            server_name: Name of server
            target: Channel name or nick
            action: Action text

        Returns:
            List of action chunks that were sent
        """
        connection = self.connections.get(server_name)
        if connection:
            return connection.send_action(target, action)
        else:
            print(f"Not connected to {server_name}")
            return []

    def send_ctcp(self, server_name: str, target: str, message: str) -> None:
        """
        Send a CTCP message

        Args:
            server_name: Name of server
            target: Target nickname
            message: CTCP message content (without \\x01 wrappers)
        """
        connection = self.connections.get(server_name)
        if connection:
            connection.send_ctcp(target, message)
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
