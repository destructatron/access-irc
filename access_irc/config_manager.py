#!/usr/bin/env python3
"""
Configuration Manager for Access IRC
Handles loading and saving configuration in JSON format
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class ConfigManager:
    """Manages application configuration stored in JSON format"""

    # System-wide data directory (for Linux distro packaging)
    SYSTEM_DATA_DIR = "/usr/share/access-irc"

    DEFAULT_CONFIG = {
        "nickname": "IRCUser",
        "realname": "Access IRC User",
        "quit_message": "Access IRC - Leaving",
        "servers": [],
        "sounds": {
            "enabled": True,
            "mention": "/usr/share/access-irc/sounds/mention.wav",
            "message": "/usr/share/access-irc/sounds/message.wav",
            "privmsg": "/usr/share/access-irc/sounds/privmsg.wav",
            "notice": "/usr/share/access-irc/sounds/notice.wav",
            "join": "/usr/share/access-irc/sounds/join.wav",
            "part": "/usr/share/access-irc/sounds/part.wav",
            "quit": "/usr/share/access-irc/sounds/quit.wav",
            "dcc_receive_complete": "/usr/share/access-irc/sounds/dcc_receive_complete.wav",
            "dcc_send_complete": "/usr/share/access-irc/sounds/dcc_send_complete.wav"
        },
        "ui": {
            "show_timestamps": True,
            "announce_all_messages": False,
            "announce_mentions_only": True,
            "announce_joins_parts": False,
            "scrollback_limit": 1000
        },
        "logging": {
            "log_directory": ""
        },
        "dcc": {
            "auto_accept": False,
            "download_directory": "",
            "port_range_start": 1024,
            "port_range_end": 65535,
            "external_ip": "",
            "announce_transfers": True
        }
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config manager

        Args:
            config_path: Path to the configuration file (defaults to ~/.config/access-irc/config.json)
        """
        if config_path is None:
            # Use XDG config directory
            config_dir = Path.home() / ".config" / "access-irc"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = str(config_dir / "config.json")
        else:
            self.config_path = config_path

        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file, creating default if doesn't exist

        Returns:
            Configuration dictionary
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                return self._merge_with_defaults(config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading config: {e}")
                print("Using default configuration")
                return self.DEFAULT_CONFIG.copy()
        else:
            # Creating new config - need to resolve sound paths for this system
            config = None

            # Try to load example config if it exists
            example_config = self._find_example_config()
            if example_config and os.path.exists(example_config):
                try:
                    with open(example_config, 'r') as f:
                        config = json.load(f)
                    config = self._merge_with_defaults(config)
                except (IOError, json.JSONDecodeError) as e:
                    print(f"Error loading example config: {e}")

            # Fallback to defaults
            if config is None:
                config = self.DEFAULT_CONFIG.copy()

            # Resolve sound paths to actual locations on this system
            config = self._resolve_sound_paths_in_config(config)

            # Save the resolved config
            self.save_config(config)
            print(f"Created config: {self.config_path}")
            return config

    def _find_example_config(self) -> Optional[str]:
        """
        Find the example config file location

        Search order:
        1. System location (/usr/share/access-irc/) for distro packages
        2. PyInstaller bundle (sys._MEIPASS)
        3. Source directory (for development)

        Returns:
            Path to example config or None if not found
        """
        import sys

        # Check system location first (for Linux distro packages)
        system_path = Path(self.SYSTEM_DATA_DIR) / "config.json.example"
        if system_path.exists():
            return str(system_path)

        # Check if running from PyInstaller bundle
        if getattr(sys, '_MEIPASS', None):
            example_path = Path(sys._MEIPASS) / "access_irc" / "data" / "config.json.example"
            if example_path.exists():
                return str(example_path)

        # Check relative to this file (for source/development installation)
        module_dir = Path(__file__).parent
        example_path = module_dir / "data" / "config.json.example"
        if example_path.exists():
            return str(example_path)

        return None

    def _resolve_sound_path(self, sound_type: str) -> Optional[str]:
        """
        Find the actual location of a sound file.

        Search order:
        1. System location (/usr/share/access-irc/sounds/)
        2. PyInstaller bundle
        3. Source/development directory

        Args:
            sound_type: Type of sound (e.g., "mention", "message")

        Returns:
            Absolute path to sound file, or None if not found
        """
        import sys

        sound_filename = f"{sound_type}.wav"

        # Check system location (for Linux distro packages)
        system_path = Path(self.SYSTEM_DATA_DIR) / "sounds" / sound_filename
        if system_path.exists():
            return str(system_path)

        # Check PyInstaller bundle
        if getattr(sys, '_MEIPASS', None):
            bundle_path = Path(sys._MEIPASS) / "access_irc" / "data" / "sounds" / sound_filename
            if bundle_path.exists():
                return str(bundle_path)

        # Check source/development directory (relative to this file)
        module_dir = Path(__file__).parent
        dev_path = module_dir / "data" / "sounds" / sound_filename
        if dev_path.exists():
            return str(dev_path)

        return None

    def _resolve_sound_paths_in_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve all sound paths in a config to actual existing locations.

        This is called when generating a new user config to ensure the saved
        paths point to files that actually exist on this system.

        Args:
            config: Configuration dictionary

        Returns:
            Config with resolved sound paths
        """
        sound_types = ["mention", "message", "privmsg", "notice", "join", "part", "quit",
                       "dcc_receive_complete", "dcc_send_complete"]

        if "sounds" not in config:
            config["sounds"] = {}

        for sound_type in sound_types:
            resolved_path = self._resolve_sound_path(sound_type)
            if resolved_path:
                config["sounds"][sound_type] = resolved_path
            # If not found, keep the default path (user may install sounds later)

        return config

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge user config with defaults to ensure all keys exist

        Args:
            config: User configuration

        Returns:
            Merged configuration
        """
        merged = self.DEFAULT_CONFIG.copy()

        # Update with user values
        for key in merged:
            if key in config:
                if isinstance(merged[key], dict) and isinstance(config[key], dict):
                    merged[key].update(config[key])
                else:
                    merged[key] = config[key]

        return merged

    def save_config(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save configuration to file atomically

        Uses a write-to-temp-then-rename strategy to prevent data loss
        if the save is interrupted. Also creates a backup of the previous
        config file.

        Args:
            config: Configuration to save (uses self.config if None)

        Returns:
            True if successful, False otherwise
        """
        if config is None:
            config = self.config

        temp_path = f"{self.config_path}.tmp"
        backup_path = f"{self.config_path}.backup"

        try:
            # Write to temporary file first
            with open(temp_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Create backup of existing config if it exists
            if os.path.exists(self.config_path):
                try:
                    shutil.copy2(self.config_path, backup_path)
                except IOError as e:
                    # Backup failure is not fatal, just warn
                    print(f"Warning: Could not create config backup: {e}")

            # Atomic rename (on POSIX systems)
            os.replace(temp_path, self.config_path)
            return True

        except IOError as e:
            print(f"Error saving config: {e}")
            # Clean up temp file if it exists
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value

        Args:
            key: Configuration key
            default: Default value if key doesn't exist

        Returns:
            Configuration value
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value

        Args:
            key: Configuration key
            value: Value to set
        """
        self.config[key] = value

    def get_servers(self) -> List[Dict[str, Any]]:
        """Get list of configured servers"""
        return self.config.get("servers", [])

    def add_server(self, server: Dict[str, Any]) -> None:
        """
        Add a server to configuration

        Args:
            server: Server configuration dict with keys: name, host, port, ssl, channels
        """
        servers = self.config.get("servers", [])
        servers.append(server)
        self.config["servers"] = servers
        self.save_config()

    def update_server(self, index: int, server: Dict[str, Any]) -> bool:
        """
        Update server at index

        Args:
            index: Index of server to update
            server: New server configuration

        Returns:
            True if successful, False if index invalid
        """
        servers = self.config.get("servers", [])
        if 0 <= index < len(servers):
            servers[index] = server
            self.config["servers"] = servers
            self.save_config()
            return True
        return False

    def remove_server(self, index: int) -> bool:
        """
        Remove server at index

        Args:
            index: Index of server to remove

        Returns:
            True if successful, False if index invalid
        """
        servers = self.config.get("servers", [])
        if 0 <= index < len(servers):
            servers.pop(index)
            self.config["servers"] = servers
            self.save_config()
            return True
        return False

    def get_nickname(self) -> str:
        """Get configured nickname"""
        return self.config.get("nickname", "IRCUser")

    def set_nickname(self, nickname: str) -> None:
        """Set nickname and save"""
        self.config["nickname"] = nickname
        self.save_config()

    def get_realname(self) -> str:
        """Get configured real name"""
        return self.config.get("realname", "Access IRC User")

    def set_realname(self, realname: str) -> None:
        """Set real name and save"""
        self.config["realname"] = realname
        self.save_config()

    def get_quit_message(self) -> str:
        """Get configured quit message"""
        return self.config.get("quit_message", "Access IRC - Leaving")

    def set_quit_message(self, quit_message: str) -> None:
        """Set quit message and save"""
        self.config["quit_message"] = quit_message
        self.save_config()

    def are_sounds_enabled(self) -> bool:
        """Check if sounds are enabled"""
        return self.config.get("sounds", {}).get("enabled", True)

    def get_sound_path(self, sound_type: str) -> Optional[str]:
        """
        Get path to sound file

        Args:
            sound_type: Type of sound (mention, message, privmsg, notice, join, part, quit)

        Returns:
            Path to sound file or None if not configured
        """
        sounds = self.config.get("sounds", {})
        return sounds.get(sound_type)

    def should_announce_all_messages(self) -> bool:
        """Check if all messages should be announced"""
        return self.config.get("ui", {}).get("announce_all_messages", False)

    def should_announce_mentions(self) -> bool:
        """Check if mentions should be announced"""
        return self.config.get("ui", {}).get("announce_mentions_only", True)

    def should_announce_joins_parts(self) -> bool:
        """Check if joins/parts should be announced"""
        return self.config.get("ui", {}).get("announce_joins_parts", False)

    def should_show_timestamps(self) -> bool:
        """Check if timestamps should be shown in messages"""
        return self.config.get("ui", {}).get("show_timestamps", True)

    def get_log_directory(self) -> str:
        """Get configured log directory"""
        return self.config.get("logging", {}).get("log_directory", "")

    def set_log_directory(self, log_directory: str) -> None:
        """
        Set log directory and save

        Args:
            log_directory: Path to log directory
        """
        if "logging" not in self.config:
            self.config["logging"] = {}
        self.config["logging"]["log_directory"] = log_directory
        self.save_config()

    def get_scrollback_limit(self) -> int:
        """Get scrollback limit (number of messages to keep in history)"""
        return self.config.get("ui", {}).get("scrollback_limit", 1000)

    def set_scrollback_limit(self, limit: int) -> None:
        """
        Set scrollback limit and save

        Args:
            limit: Number of messages to keep in scrollback (0 = unlimited)
        """
        if "ui" not in self.config:
            self.config["ui"] = {}
        self.config["ui"]["scrollback_limit"] = limit
        self.save_config()

    # DCC configuration methods

    def get_dcc_config(self) -> Dict[str, Any]:
        """Get DCC configuration section"""
        return self.config.get("dcc", self.DEFAULT_CONFIG["dcc"].copy())

    def get_dcc_auto_accept(self) -> bool:
        """Check if DCC auto-accept is enabled"""
        return self.config.get("dcc", {}).get("auto_accept", False)

    def set_dcc_auto_accept(self, enabled: bool) -> None:
        """Set DCC auto-accept setting"""
        if "dcc" not in self.config:
            self.config["dcc"] = {}
        self.config["dcc"]["auto_accept"] = enabled
        self.save_config()

    def get_dcc_download_directory(self) -> str:
        """Get DCC download directory"""
        return self.config.get("dcc", {}).get("download_directory", "")

    def set_dcc_download_directory(self, directory: str) -> None:
        """Set DCC download directory"""
        if "dcc" not in self.config:
            self.config["dcc"] = {}
        self.config["dcc"]["download_directory"] = directory
        self.save_config()

    def get_dcc_port_range(self) -> Tuple[int, int]:
        """Get DCC port range (start, end)"""
        dcc = self.config.get("dcc", {})
        return (dcc.get("port_range_start", 1024), dcc.get("port_range_end", 65535))

    def set_dcc_port_range(self, start: int, end: int) -> None:
        """Set DCC port range"""
        if "dcc" not in self.config:
            self.config["dcc"] = {}
        self.config["dcc"]["port_range_start"] = start
        self.config["dcc"]["port_range_end"] = end
        self.save_config()

    def get_dcc_external_ip(self) -> str:
        """Get DCC external IP address for NAT"""
        return self.config.get("dcc", {}).get("external_ip", "")

    def set_dcc_external_ip(self, ip: str) -> None:
        """Set DCC external IP address"""
        if "dcc" not in self.config:
            self.config["dcc"] = {}
        self.config["dcc"]["external_ip"] = ip
        self.save_config()

    def should_announce_dcc_transfers(self) -> bool:
        """Check if DCC transfers should be announced to screen reader"""
        return self.config.get("dcc", {}).get("announce_transfers", True)

    def set_dcc_announce_transfers(self, enabled: bool) -> None:
        """Set whether DCC transfers should be announced"""
        if "dcc" not in self.config:
            self.config["dcc"] = {}
        self.config["dcc"]["announce_transfers"] = enabled
        self.save_config()


if __name__ == "__main__":
    # Test config manager
    config = ConfigManager("test_config.json")

    # Add a test server
    config.add_server({
        "name": "Libera.Chat",
        "host": "irc.libera.chat",
        "port": 6667,
        "ssl": False,
        "channels": ["#python", "#gtk"]
    })

    print("Servers:", config.get_servers())
    print("Nickname:", config.get_nickname())
    print("Sounds enabled:", config.are_sounds_enabled())
