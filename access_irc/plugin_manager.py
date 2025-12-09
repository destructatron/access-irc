"""
Plugin Manager for Access IRC

Handles plugin discovery, loading, and hook execution.
"""

import os
import sys
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from gi.repository import GLib

try:
    import pluggy
    PLUGGY_AVAILABLE = True
except ImportError:
    PLUGGY_AVAILABLE = False
    print("Warning: pluggy not available. Plugin support will be disabled.")

from .plugin_specs import AccessIRCHookSpec, hookimpl


class PluginContext:
    """
    Context object passed to plugins providing safe access to application APIs.

    This is the main interface plugins use to interact with Access IRC.
    """

    def __init__(self, plugin_manager: 'PluginManager'):
        self._pm = plugin_manager
        self._timers: Dict[str, int] = {}  # timer_id -> GLib source id

    # =========================================================================
    # IRC Operations
    # =========================================================================

    def send_message(self, server: str, target: str, message: str) -> bool:
        """Send a message to a channel or user.

        Args:
            server: Server name
            target: Channel or nick
            message: Message to send

        Returns:
            True if sent successfully
        """
        if not self._pm.irc_manager:
            return False

        def do_send():
            sent_chunks = self._pm.irc_manager.send_message(server, target, message)
            # Show in our own view
            if self._pm.window and sent_chunks:
                connection = self._pm.irc_manager.connections.get(server)
                our_nick = connection.nickname if connection else "You"
                for chunk in sent_chunks:
                    self._pm.window.add_message(server, target, our_nick, chunk)
            return False

        GLib.idle_add(do_send)
        return True

    def send_action(self, server: str, target: str, action: str) -> bool:
        """Send a CTCP ACTION (/me) to a channel or user.

        Args:
            server: Server name
            target: Channel or nick
            action: Action text

        Returns:
            True if sent successfully
        """
        if not self._pm.irc_manager:
            return False

        def do_send():
            sent_chunks = self._pm.irc_manager.send_action(server, target, action)
            if self._pm.window and sent_chunks:
                connection = self._pm.irc_manager.connections.get(server)
                our_nick = connection.nickname if connection else "You"
                for chunk in sent_chunks:
                    self._pm.window.add_action_message(server, target, our_nick, chunk)
            return False

        GLib.idle_add(do_send)
        return True

    def send_notice(self, server: str, target: str, message: str) -> bool:
        """Send a NOTICE to a channel or user.

        Args:
            server: Server name
            target: Channel or nick
            message: Notice text

        Returns:
            True if sent successfully
        """
        if not self._pm.irc_manager:
            return False

        def do_send():
            connection = self._pm.irc_manager.connections.get(server)
            if connection and connection.irc:
                connection.irc.quote(f"NOTICE {target} :{message}")
            return False

        GLib.idle_add(do_send)
        return True

    def send_raw(self, server: str, command: str) -> bool:
        """Send a raw IRC command.

        Args:
            server: Server name
            command: Raw IRC command

        Returns:
            True if sent successfully
        """
        if not self._pm.irc_manager:
            return False

        def do_send():
            connection = self._pm.irc_manager.connections.get(server)
            if connection and connection.irc:
                connection.irc.quote(command)
            return False

        GLib.idle_add(do_send)
        return True

    def join_channel(self, server: str, channel: str) -> bool:
        """Join a channel.

        Args:
            server: Server name
            channel: Channel to join

        Returns:
            True if command sent
        """
        if not self._pm.irc_manager:
            return False
        self._pm.irc_manager.join_channel(server, channel)
        return True

    def part_channel(self, server: str, channel: str, reason: str = "") -> bool:
        """Leave a channel.

        Args:
            server: Server name
            channel: Channel to leave
            reason: Part reason

        Returns:
            True if command sent
        """
        if not self._pm.irc_manager:
            return False
        self._pm.irc_manager.part_channel(server, channel, reason)
        return True

    # =========================================================================
    # UI Operations
    # =========================================================================

    def add_system_message(self, server: str, target: str, message: str,
                          announce: bool = False) -> None:
        """Add a system message to a channel/PM buffer.

        Args:
            server: Server name
            target: Channel or PM target
            message: Message to display
            announce: Whether to announce to screen reader
        """
        if not self._pm.window:
            return

        def do_add():
            self._pm.window.add_system_message(server, target, message, announce)
            return False

        GLib.idle_add(do_add)

    def announce(self, message: str) -> None:
        """Announce a message to the screen reader.

        Args:
            message: Message to announce
        """
        if not self._pm.window:
            return

        def do_announce():
            self._pm.window.announce_to_screen_reader(message)
            return False

        GLib.idle_add(do_announce)

    def play_sound(self, sound_type: str) -> None:
        """Play a sound.

        Args:
            sound_type: One of 'message', 'mention', 'notice', 'join', 'part'
        """
        if not self._pm.sound_manager:
            return
        self._pm.sound_manager.play(sound_type)

    # =========================================================================
    # Information Getters
    # =========================================================================

    def get_current_server(self) -> Optional[str]:
        """Get the currently selected server name."""
        if self._pm.window:
            return self._pm.window.current_server
        return None

    def get_current_target(self) -> Optional[str]:
        """Get the currently selected channel or PM target."""
        if self._pm.window:
            return self._pm.window.current_target
        return None

    def get_nickname(self, server: str) -> Optional[str]:
        """Get our nickname on a server.

        Args:
            server: Server name

        Returns:
            Our nickname or None if not connected
        """
        if not self._pm.irc_manager:
            return None
        connection = self._pm.irc_manager.connections.get(server)
        if connection:
            return connection.nickname
        return None

    def get_connected_servers(self) -> List[str]:
        """Get list of connected server names."""
        if not self._pm.irc_manager:
            return []
        with self._pm.irc_manager._connections_lock:
            return [name for name, conn in self._pm.irc_manager.connections.items()
                    if conn.connected]

    def get_channels(self, server: str) -> List[str]:
        """Get list of channels we're in on a server.

        Args:
            server: Server name

        Returns:
            List of channel names
        """
        if not self._pm.irc_manager:
            return []
        connection = self._pm.irc_manager.connections.get(server)
        if connection:
            return list(connection.current_channels)
        return []

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Config key (dot-separated for nested, e.g., 'ui.announce_all_messages')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        if not self._pm.config_manager:
            return default

        # Support dot notation for nested keys
        keys = key.split('.')
        value = self._pm.config_manager.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    # =========================================================================
    # Timer Operations
    # =========================================================================

    def add_timer(self, timer_id: str, interval_ms: int, callback: Callable[[], bool]) -> bool:
        """Add a repeating timer.

        Args:
            timer_id: Unique identifier for this timer
            interval_ms: Interval in milliseconds
            callback: Function to call. Return True to continue, False to stop.

        Returns:
            True if timer was added
        """
        if timer_id in self._timers:
            return False

        def wrapper():
            try:
                return callback()
            except Exception as e:
                print(f"Plugin timer error ({timer_id}): {e}")
                return False

        source_id = GLib.timeout_add(interval_ms, wrapper)
        self._timers[timer_id] = source_id
        return True

    def remove_timer(self, timer_id: str) -> bool:
        """Remove a timer.

        Args:
            timer_id: Timer identifier

        Returns:
            True if timer was removed
        """
        if timer_id not in self._timers:
            return False

        GLib.source_remove(self._timers[timer_id])
        del self._timers[timer_id]
        return True

    def add_timeout(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """Add a one-shot timeout.

        Args:
            delay_ms: Delay in milliseconds
            callback: Function to call once
        """
        def wrapper():
            try:
                callback()
            except Exception as e:
                print(f"Plugin timeout error: {e}")
            return False

        GLib.timeout_add(delay_ms, wrapper)

    def _cleanup_timers(self) -> None:
        """Clean up all timers (called on shutdown)."""
        for source_id in self._timers.values():
            GLib.source_remove(source_id)
        self._timers.clear()


class PluginManager:
    """
    Manages plugin discovery, loading, and hook execution.
    """

    def __init__(self):
        self.plugins_dir: Optional[Path] = None
        self.loaded_plugins: Dict[str, Any] = {}
        self.pm: Optional[pluggy.PluginManager] = None
        self.ctx: Optional[PluginContext] = None

        # References to application components (set via set_managers)
        self.irc_manager = None
        self.config_manager = None
        self.sound_manager = None
        self.log_manager = None
        self.window = None

        if PLUGGY_AVAILABLE:
            self.pm = pluggy.PluginManager("access_irc")
            self.pm.add_hookspecs(AccessIRCHookSpec)
            self.ctx = PluginContext(self)

    def set_managers(self, irc_manager, config_manager, sound_manager, log_manager, window) -> None:
        """Set references to application managers.

        Args:
            irc_manager: IRCManager instance
            config_manager: ConfigManager instance
            sound_manager: SoundManager instance
            log_manager: LogManager instance
            window: AccessibleIRCWindow instance
        """
        self.irc_manager = irc_manager
        self.config_manager = config_manager
        self.sound_manager = sound_manager
        self.log_manager = log_manager
        self.window = window

        # Set plugins directory from config or default
        if config_manager:
            config_dir = Path(os.path.expanduser("~/.config/access-irc"))
            self.plugins_dir = config_dir / "plugins"

    def discover_and_load_plugins(self) -> int:
        """Discover and load all plugins from the plugins directory.

        Returns:
            Number of plugins loaded
        """
        if not PLUGGY_AVAILABLE or not self.pm:
            return 0

        if not self.plugins_dir:
            return 0

        # Create plugins directory if it doesn't exist
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        loaded = 0

        # Load Python files from plugins directory
        for plugin_file in self.plugins_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue

            try:
                if self._load_plugin_file(plugin_file):
                    loaded += 1
            except Exception as e:
                print(f"Error loading plugin {plugin_file.name}: {e}")

        # Load plugin packages (directories with __init__.py)
        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists():
                if plugin_dir.name.startswith("_"):
                    continue

                try:
                    if self._load_plugin_package(plugin_dir):
                        loaded += 1
                except Exception as e:
                    print(f"Error loading plugin package {plugin_dir.name}: {e}")

        return loaded

    def _load_plugin_file(self, plugin_file: Path) -> bool:
        """Load a single plugin file.

        Args:
            plugin_file: Path to plugin .py file

        Returns:
            True if loaded successfully
        """
        plugin_name = plugin_file.stem

        if plugin_name in self.loaded_plugins:
            print(f"Plugin {plugin_name} already loaded")
            return False

        # Load the module
        spec = importlib.util.spec_from_file_location(
            f"access_irc_plugin_{plugin_name}",
            plugin_file
        )
        if spec is None or spec.loader is None:
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error executing plugin {plugin_name}: {e}")
            del sys.modules[spec.name]
            return False

        # Look for plugin class or register hooks directly from module
        plugin_instance = None

        # Check for a Plugin class
        if hasattr(module, 'Plugin'):
            try:
                plugin_instance = module.Plugin()
            except Exception as e:
                print(f"Error instantiating Plugin class in {plugin_name}: {e}")
                del sys.modules[spec.name]
                return False
        # Check for a setup function that returns a plugin instance
        elif hasattr(module, 'setup'):
            try:
                plugin_instance = module.setup(self.ctx)
            except Exception as e:
                print(f"Error in setup() for {plugin_name}: {e}")
                del sys.modules[spec.name]
                return False
        else:
            # Use the module itself as a plugin (for simple scripts)
            plugin_instance = module

        # Register with pluggy
        self.pm.register(plugin_instance, name=plugin_name)
        self.loaded_plugins[plugin_name] = {
            'module': module,
            'instance': plugin_instance,
            'file': plugin_file
        }

        print(f"Loaded plugin: {plugin_name}")
        return True

    def _load_plugin_package(self, plugin_dir: Path) -> bool:
        """Load a plugin package (directory).

        Args:
            plugin_dir: Path to plugin directory

        Returns:
            True if loaded successfully
        """
        plugin_name = plugin_dir.name
        return self._load_plugin_file(plugin_dir / "__init__.py")

    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin.

        Args:
            plugin_name: Name of plugin to unload

        Returns:
            True if unloaded successfully
        """
        if not PLUGGY_AVAILABLE or not self.pm:
            return False

        if plugin_name not in self.loaded_plugins:
            return False

        plugin_info = self.loaded_plugins[plugin_name]

        # Unregister from pluggy
        self.pm.unregister(name=plugin_name)

        # Remove from sys.modules
        module_name = f"access_irc_plugin_{plugin_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        del self.loaded_plugins[plugin_name]
        print(f"Unloaded plugin: {plugin_name}")
        return True

    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin.

        Args:
            plugin_name: Name of plugin to reload

        Returns:
            True if reloaded successfully
        """
        if plugin_name not in self.loaded_plugins:
            return False

        plugin_file = self.loaded_plugins[plugin_name]['file']
        self.unload_plugin(plugin_name)
        return self._load_plugin_file(plugin_file)

    def get_loaded_plugins(self) -> List[str]:
        """Get list of loaded plugin names."""
        return list(self.loaded_plugins.keys())

    # =========================================================================
    # Hook Callers
    # =========================================================================

    def call_startup(self) -> None:
        """Call on_startup hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_startup(ctx=self.ctx)
            except Exception as e:
                print(f"Plugin error in on_startup: {e}")

    def call_shutdown(self) -> None:
        """Call on_shutdown hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_shutdown(ctx=self.ctx)
            except Exception as e:
                print(f"Plugin error in on_shutdown: {e}")

            # Clean up timers
            self.ctx._cleanup_timers()

    def call_connect(self, server: str) -> None:
        """Call on_connect hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_connect(ctx=self.ctx, server=server)
            except Exception as e:
                print(f"Plugin error in on_connect: {e}")

    def call_disconnect(self, server: str) -> None:
        """Call on_disconnect hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_disconnect(ctx=self.ctx, server=server)
            except Exception as e:
                print(f"Plugin error in on_disconnect: {e}")

    def filter_incoming_message(self, server: str, target: str, sender: str,
                                message: str) -> Optional[Dict[str, Any]]:
        """Call filter_incoming_message hooks.

        Returns:
            None to allow unchanged, or dict with modifications/block
        """
        if self.pm and self.ctx:
            try:
                return self.pm.hook.filter_incoming_message(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, message=message
                )
            except Exception as e:
                print(f"Plugin error in filter_incoming_message: {e}")
        return None

    def filter_incoming_action(self, server: str, target: str, sender: str,
                               action: str) -> Optional[Dict[str, Any]]:
        """Call filter_incoming_action hooks."""
        if self.pm and self.ctx:
            try:
                return self.pm.hook.filter_incoming_action(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, action=action
                )
            except Exception as e:
                print(f"Plugin error in filter_incoming_action: {e}")
        return None

    def filter_incoming_notice(self, server: str, target: str, sender: str,
                               message: str) -> Optional[Dict[str, Any]]:
        """Call filter_incoming_notice hooks."""
        if self.pm and self.ctx:
            try:
                return self.pm.hook.filter_incoming_notice(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, message=message
                )
            except Exception as e:
                print(f"Plugin error in filter_incoming_notice: {e}")
        return None

    def filter_outgoing_message(self, server: str, target: str,
                                message: str) -> Optional[Dict[str, Any]]:
        """Call filter_outgoing_message hooks."""
        if self.pm and self.ctx:
            try:
                return self.pm.hook.filter_outgoing_message(
                    ctx=self.ctx, server=server, target=target, message=message
                )
            except Exception as e:
                print(f"Plugin error in filter_outgoing_message: {e}")
        return None

    def call_message(self, server: str, target: str, sender: str,
                     message: str, is_mention: bool) -> None:
        """Call on_message hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_message(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, message=message, is_mention=is_mention
                )
            except Exception as e:
                print(f"Plugin error in on_message: {e}")

    def call_action(self, server: str, target: str, sender: str,
                    action: str, is_mention: bool) -> None:
        """Call on_action hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_action(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, action=action, is_mention=is_mention
                )
            except Exception as e:
                print(f"Plugin error in on_action: {e}")

    def call_notice(self, server: str, target: str, sender: str, message: str) -> None:
        """Call on_notice hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_notice(
                    ctx=self.ctx, server=server, target=target,
                    sender=sender, message=message
                )
            except Exception as e:
                print(f"Plugin error in on_notice: {e}")

    def call_join(self, server: str, channel: str, nick: str) -> None:
        """Call on_join hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_join(ctx=self.ctx, server=server,
                                     channel=channel, nick=nick)
            except Exception as e:
                print(f"Plugin error in on_join: {e}")

    def call_part(self, server: str, channel: str, nick: str, reason: str) -> None:
        """Call on_part hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_part(ctx=self.ctx, server=server,
                                     channel=channel, nick=nick, reason=reason)
            except Exception as e:
                print(f"Plugin error in on_part: {e}")

    def call_quit(self, server: str, nick: str, reason: str) -> None:
        """Call on_quit hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_quit(ctx=self.ctx, server=server,
                                     nick=nick, reason=reason)
            except Exception as e:
                print(f"Plugin error in on_quit: {e}")

    def call_nick(self, server: str, old_nick: str, new_nick: str) -> None:
        """Call on_nick hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_nick(ctx=self.ctx, server=server,
                                     old_nick=old_nick, new_nick=new_nick)
            except Exception as e:
                print(f"Plugin error in on_nick: {e}")

    def call_kick(self, server: str, channel: str, kicked: str,
                  kicker: str, reason: str) -> None:
        """Call on_kick hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_kick(ctx=self.ctx, server=server, channel=channel,
                                     kicked=kicked, kicker=kicker, reason=reason)
            except Exception as e:
                print(f"Plugin error in on_kick: {e}")

    def call_topic(self, server: str, channel: str, topic: str,
                   setter: Optional[str]) -> None:
        """Call on_topic hooks."""
        if self.pm and self.ctx:
            try:
                self.pm.hook.on_topic(ctx=self.ctx, server=server,
                                      channel=channel, topic=topic, setter=setter)
            except Exception as e:
                print(f"Plugin error in on_topic: {e}")

    def call_command(self, server: str, target: str, command: str, args: str) -> bool:
        """Call on_command hooks.

        Returns:
            True if a plugin handled the command
        """
        if self.pm and self.ctx:
            try:
                result = self.pm.hook.on_command(
                    ctx=self.ctx, server=server, target=target,
                    command=command, args=args
                )
                return result is True
            except Exception as e:
                print(f"Plugin error in on_command: {e}")
        return False
