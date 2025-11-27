#!/usr/bin/env python3
"""
Configuration Manager for Access IRC
Handles loading and saving configuration in JSON format
"""

import json
import os
from typing import Dict, List, Any, Optional


class ConfigManager:
    """Manages application configuration stored in JSON format"""

    DEFAULT_CONFIG = {
        "nickname": "IRCUser",
        "realname": "Access IRC User",
        "servers": [],
        "sounds": {
            "enabled": True,
            "mention": "sounds/mention.wav",
            "message": "sounds/message.wav",
            "join": "sounds/join.wav",
            "part": "sounds/part.wav"
        },
        "ui": {
            "show_timestamps": True,
            "announce_all_messages": False,
            "announce_mentions_only": True,
            "announce_joins_parts": False
        }
    }

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize config manager

        Args:
            config_path: Path to the configuration file
        """
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
            # Create default config file
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

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

    def are_sounds_enabled(self) -> bool:
        """Check if sounds are enabled"""
        return self.config.get("sounds", {}).get("enabled", True)

    def get_sound_path(self, sound_type: str) -> Optional[str]:
        """
        Get path to sound file

        Args:
            sound_type: Type of sound (mention, message, join, part)

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
