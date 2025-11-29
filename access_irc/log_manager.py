#!/usr/bin/env python3
"""
Log Manager for Access IRC
Handles logging of IRC conversations to disk
"""

import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional


class LogManager:
    """Manages IRC conversation logging"""

    def __init__(self, log_directory: Optional[str] = None):
        """
        Initialize log manager

        Args:
            log_directory: Base directory for logs (None to disable logging)
        """
        self.log_directory = log_directory
        self.enabled = log_directory is not None and log_directory.strip() != ""
        self._write_lock = threading.Lock()  # Protect concurrent writes

        # Create base log directory if it doesn't exist
        if self.enabled:
            self._ensure_directory_exists(self.log_directory)

    def set_log_directory(self, log_directory: str, connected_servers: list = None) -> None:
        """
        Set or update the log directory

        Args:
            log_directory: Path to log directory
            connected_servers: List of currently connected server names (optional)
        """
        self.log_directory = log_directory
        self.enabled = log_directory is not None and log_directory.strip() != ""

        if self.enabled:
            if not self._ensure_directory_exists(self.log_directory):
                raise OSError(f"Failed to create log directory: {self.log_directory}")

            # Proactively create directories for connected servers
            failed_servers = []
            if connected_servers:
                for server_name in connected_servers:
                    # Skip invalid server names
                    if not server_name or not server_name.strip():
                        continue

                    server_dir = Path(self.log_directory) / self._sanitize_name(server_name)
                    if not self._ensure_directory_exists(str(server_dir)):
                        failed_servers.append(server_name)

            if failed_servers:
                raise OSError(f"Failed to create directories for: {', '.join(failed_servers)}")

    def _ensure_directory_exists(self, directory: str) -> bool:
        """
        Ensure a directory exists, creating it if necessary

        Args:
            directory: Directory path

        Returns:
            True if directory exists or was created successfully
        """
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
            return True
        except (OSError, PermissionError) as e:
            print(f"Failed to create directory {directory}: {e}")
            return False

    def _get_log_file_path(self, server: str, target: str) -> Optional[str]:
        """
        Get the log file path for a server and target

        Args:
            server: Server name
            target: Channel or PM target

        Returns:
            Path to log file or None if logging disabled
        """
        if not self.enabled or not self.log_directory:
            return None

        # Create server subdirectory
        server_dir = Path(self.log_directory) / self._sanitize_name(server)
        if not self._ensure_directory_exists(str(server_dir)):
            return None

        # Create log filename with date: channel-YYYY-MM-DD.log
        date_str = datetime.now().strftime("%Y-%m-%d")
        sanitized_target = self._sanitize_name(target)
        filename = f"{sanitized_target}-{date_str}.log"

        return str(server_dir / filename)

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize a name for use in file paths

        Args:
            name: Name to sanitize (server or channel)

        Returns:
            Sanitized name safe for file paths
        """
        # Replace characters that might be problematic in filenames
        # Keep #, letters, numbers, hyphens, underscores
        # Remove null bytes and path traversal sequences first (security)
        safe_name = name.replace("\x00", "").replace("..", "")
        safe_name = safe_name.replace("/", "-").replace("\\", "-")
        safe_name = safe_name.replace(":", "-").replace("*", "-")
        safe_name = safe_name.replace("?", "-").replace('"', "-")
        safe_name = safe_name.replace("<", "-").replace(">", "-")
        safe_name = safe_name.replace("|", "-")

        # Prevent empty names or names that are just dots/spaces
        safe_name = safe_name.strip(". ")
        if not safe_name:
            safe_name = "unnamed"

        # Limit length to prevent filesystem issues (leave room for date suffix)
        if len(safe_name) > 200:
            safe_name = safe_name[:200]

        return safe_name

    def _write_to_log(self, server: str, target: str, line: str) -> bool:
        """
        Write a line to the appropriate log file

        Args:
            server: Server name
            target: Channel or PM target
            line: Line to write (should include timestamp)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        log_file = self._get_log_file_path(server, target)
        if not log_file:
            return False

        try:
            # Use lock to protect against concurrent writes from multiple threads
            with self._write_lock:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            return True
        except (OSError, PermissionError) as e:
            print(f"Failed to write to log file {log_file}: {e}")
            return False

    def log_message(self, server: str, target: str, sender: str, message: str) -> None:
        """
        Log a regular message

        Args:
            server: Server name
            target: Channel or PM target
            sender: Message sender
            message: Message text
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} <{sender}> {message}"
        self._write_to_log(server, target, line)

    def log_action(self, server: str, target: str, sender: str, action: str) -> None:
        """
        Log a CTCP ACTION message (/me)

        Args:
            server: Server name
            target: Channel or PM target
            sender: Action sender
            action: Action text
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} * {sender} {action}"
        self._write_to_log(server, target, line)

    def log_notice(self, server: str, target: str, sender: str, message: str) -> None:
        """
        Log a NOTICE message

        Args:
            server: Server name
            target: Channel or server (for private notices)
            sender: Notice sender
            message: Notice text
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} -{sender}- {message}"
        self._write_to_log(server, target, line)

    def log_join(self, server: str, channel: str, nick: str) -> None:
        """
        Log a user join

        Args:
            server: Server name
            channel: Channel name
            nick: User nickname
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} --> {nick} has joined {channel}"
        self._write_to_log(server, channel, line)

    def log_part(self, server: str, channel: str, nick: str, reason: str = "") -> None:
        """
        Log a user part

        Args:
            server: Server name
            channel: Channel name
            nick: User nickname
            reason: Part reason (optional)
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        if reason:
            line = f"{timestamp} <-- {nick} has left {channel} ({reason})"
        else:
            line = f"{timestamp} <-- {nick} has left {channel}"
        self._write_to_log(server, channel, line)

    def log_quit(self, server: str, channel: str, nick: str, reason: str = "") -> None:
        """
        Log a user quit

        Args:
            server: Server name
            channel: Channel where quit is visible
            nick: User nickname
            reason: Quit reason (optional)
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        if reason:
            line = f"{timestamp} <-- {nick} has quit ({reason})"
        else:
            line = f"{timestamp} <-- {nick} has quit"
        self._write_to_log(server, channel, line)

    def log_nick(self, server: str, channel: str, old_nick: str, new_nick: str) -> None:
        """
        Log a nick change

        Args:
            server: Server name
            channel: Channel where change is visible
            old_nick: Old nickname
            new_nick: New nickname
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} --- {old_nick} is now known as {new_nick}"
        self._write_to_log(server, channel, line)

    def log_kick(self, server: str, channel: str, kicker: str, kicked: str, reason: str = "") -> None:
        """
        Log a user kick

        Args:
            server: Server name
            channel: Channel name
            kicker: User who kicked
            kicked: User who was kicked
            reason: Kick reason (optional)
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        if reason:
            line = f"{timestamp} <-! {kicked} was kicked by {kicker} ({reason})"
        else:
            line = f"{timestamp} <-! {kicked} was kicked by {kicker}"
        self._write_to_log(server, channel, line)

    def log_system(self, server: str, target: str, message: str) -> None:
        """
        Log a system message

        Args:
            server: Server name
            target: Channel or server
            message: System message
        """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        line = f"{timestamp} * {message}"
        self._write_to_log(server, target, line)
