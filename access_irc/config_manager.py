#!/usr/bin/env python3
"""
Configuration Manager for Access IRC
Handles loading and saving configuration in JSON format
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional


class ConfigManager:
    """Manages application configuration stored in JSON format"""

    DEFAULT_CONFIG = {
        "nickname": "IRCUser",
        "realname": "Access IRC User",
        "quit_message": "Access IRC - Leaving",
        "servers": [],
        "sounds": {
            "enabled": True,
            "mention": "access_irc/data/sounds/mention.wav",
            "message": "access_irc/data/sounds/message.wav",
            "privmsg": "access_irc/data/sounds/privmsg.wav",
            "notice": "access_irc/data/sounds/notice.wav",
            "join": "access_irc/data/sounds/join.wav",
            "part": "access_irc/data/sounds/part.wav",
            "quit": "access_irc/data/sounds/quit.wav"
        },
        "ui": {
            "show_timestamps": True,
            "announce_all_messages": False,
            "announce_mentions_only": True,
            "announce_joins_parts": False
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
            # Try to copy example config if it exists
            example_config = self._find_example_config()
            if example_config and os.path.exists(example_config):
                try:
                    shutil.copy(example_config, self.config_path)
                    print(f"Created config from example: {self.config_path}")
                    with open(self.config_path, 'r') as f:
                        config = json.load(f)
                    return self._merge_with_defaults(config)
                except (IOError, json.JSONDecodeError) as e:
                    print(f"Error copying example config: {e}")

            # Fallback: create default config file
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

    def _find_example_config(self) -> Optional[str]:
        """
        Find the example config file location

        Checks for PyInstaller bundle (sys._MEIPASS) and source directory

        Returns:
            Path to example config or None if not found
        """
        import sys

        # Check if running from PyInstaller bundle
        if getattr(sys, '_MEIPASS', None):
            example_path = Path(sys._MEIPASS) / "access_irc" / "data" / "config.json.example"
            if example_path.exists():
                return str(example_path)

        # Check relative to this file (for source installation)
        module_dir = Path(__file__).parent
        example_path = module_dir / "data" / "config.json.example"
        if example_path.exists():
            return str(example_path)

        return None

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
        Save configuration to file

        Args:
            config: Configuration to save (uses self.config if None)

        Returns:
            True if successful, False otherwise
        """
        if config is None:
            config = self.config

        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except IOError as e:
            print(f"Error saving config: {e}")
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
