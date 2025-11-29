"""
Access IRC - An accessible IRC client for Linux with screen reader support
"""

__version__ = "1.1.0"
__author__ = "Access IRC Contributors"
__license__ = "MIT"

from .config_manager import ConfigManager
from .sound_manager import SoundManager
from .irc_manager import IRCManager, IRCConnection
from .gui import AccessibleIRCWindow

__all__ = [
    "ConfigManager",
    "SoundManager",
    "IRCManager",
    "IRCConnection",
    "AccessibleIRCWindow",
]
