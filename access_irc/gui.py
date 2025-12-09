#!/usr/bin/env python3
"""
GUI for Access IRC
GTK 3 based accessible interface with AT-SPI2 support
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from typing import Optional, Dict, Tuple
from datetime import datetime
import subprocess

# Try to import gtkspell for spell checking
try:
    gi.require_version('Gspell', '1')
    from gi.repository import Gspell
    GSPELL_AVAILABLE = True
except (ValueError, ImportError):
    GSPELL_AVAILABLE = False
    print("Warning: Gspell not available. Spell checking will be disabled.")


class AccessibleIRCWindow(Gtk.Window):
    """Main window for accessible IRC client"""

    # UI Layout Constants
    DEFAULT_WINDOW_WIDTH = 1200
    DEFAULT_WINDOW_HEIGHT = 800
    MIN_WINDOW_WIDTH = 900
    MIN_WINDOW_HEIGHT = 600
    WINDOW_BORDER_WIDTH = 6

    # Panel dimensions
    LEFT_PANEL_WIDTH = 250  # Width of server/channel tree
    USERS_LIST_WIDTH = 200  # Width of users list
    LEFT_PANEL_WITH_BORDERS = 270  # LEFT_PANEL_WIDTH + borders + spacing

    def __init__(self, app_title: str = "Access IRC"):
        """
        Initialize main window

        Args:
            app_title: Application window title
        """
        super().__init__(title=app_title)
        self.app_title = app_title  # Store for dynamic title updates
        # Use a larger default size to ensure all panels are visible
        self.set_default_size(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT)
        # Set minimum size to ensure all UI elements are visible
        self.set_size_request(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.set_border_width(self.WINDOW_BORDER_WIDTH)

        # Store references for callbacks
        self.irc_manager = None
        self.sound_manager = None
        self.config_manager = None

        # Current context
        self.current_server: Optional[str] = None
        self.current_target: Optional[str] = None  # Channel or PM recipient

        # Message buffers for each server/channel
        self.message_buffers: Dict[Tuple[str, str], Gtk.TextBuffer] = {}

        # Track PM tree iters per server: Dict[server_name, Dict[username, TreeIter]]
        self.pm_iters: Dict[str, Dict[str, Gtk.TreeIter]] = {}

        # Track "Private Messages" folder iter per server: Dict[server_name, TreeIter]
        self.pm_folder_iters: Dict[str, Gtk.TreeIter] = {}

        # Track "Mentions" buffer iter per server: Dict[server_name, TreeIter]
        self.mentions_iters: Dict[str, Gtk.TreeIter] = {}

        # Reference to paned widget for resizing
        self.h_paned = None

        # Reference to users list widget
        self.users_list = None

        # Tab completion state
        self.tab_completion_matches = []
        self.tab_completion_index = 0
        self.tab_completion_word_start = 0
        self.tab_completion_original_after = ""

        # Temporary announcement mode (can be toggled with Ctrl+S without saving)
        # None means use config settings, otherwise overrides config
        # Values: "all", "mentions", "none"
        self.temp_announcement_mode = None

        # Per-channel announcement override (toggled with F2)
        # Key: (server_name, target), Value: True (enabled), False (disabled), or None (use fallback)
        # When None or missing, falls back to temp_announcement_mode then config
        self.channel_announcement_overrides: Dict[Tuple[str, str], Optional[bool]] = {}

        # Build UI
        self._build_ui()

        # Connect to realize signal to set paned position after window is sized
        self.connect("realize", self._on_window_realized)

        # Connect to size-allocate to update paned positions when window is resized
        self.connect("size-allocate", self._on_window_size_allocate)

        # Connect key press for window-level shortcuts (like Ctrl+W)
        self.connect("key-press-event", self.on_window_key_press)

    def _build_ui(self) -> None:
        """Build the user interface"""

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(main_box)

        # Menu bar
        menubar = self._create_menubar()
        main_box.pack_start(menubar, False, False, 0)

        # Main content area with paned layout
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        # Position will be set in _on_window_realized
        main_box.pack_start(self.main_paned, True, True, 0)

        # Left side: Server and channel list
        left_panel = self._create_left_panel()
        self.main_paned.add1(left_panel)

        # Right side: Chat area
        right_panel = self._create_right_panel()
        self.main_paned.add2(right_panel)

        # Status bar
        self.statusbar = Gtk.Statusbar()
        self.statusbar_context = self.statusbar.get_context_id("main")
        main_box.pack_start(self.statusbar, False, False, 0)

    def _create_menubar(self) -> Gtk.MenuBar:
        """Create application menu bar"""

        menubar = Gtk.MenuBar()

        # Server menu
        server_menu = Gtk.Menu()
        server_item = Gtk.MenuItem.new_with_mnemonic("_Server")
        server_item.set_submenu(server_menu)

        connect_item = Gtk.MenuItem.new_with_mnemonic("_Connect to Server...")
        connect_item.connect("activate", self.on_connect_server)
        server_menu.append(connect_item)

        manage_item = Gtk.MenuItem.new_with_mnemonic("_Manage Servers...")
        manage_item.connect("activate", self.on_manage_servers)
        server_menu.append(manage_item)

        server_menu.append(Gtk.SeparatorMenuItem())

        disconnect_item = Gtk.MenuItem.new_with_mnemonic("_Disconnect")
        disconnect_item.connect("activate", self.on_disconnect_server)
        server_menu.append(disconnect_item)

        server_menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem.new_with_mnemonic("_Quit")
        quit_item.connect("activate", self.on_quit)
        server_menu.append(quit_item)

        menubar.append(server_item)

        # Channel menu
        channel_menu = Gtk.Menu()
        channel_item = Gtk.MenuItem.new_with_mnemonic("_Channel")
        channel_item.set_submenu(channel_menu)

        join_item = Gtk.MenuItem.new_with_mnemonic("_Join Channel...")
        join_item.connect("activate", self.on_join_channel)
        channel_menu.append(join_item)

        part_item = Gtk.MenuItem.new_with_mnemonic("_Leave Channel")
        part_item.connect("activate", self.on_part_channel)
        channel_menu.append(part_item)

        channel_menu.append(Gtk.SeparatorMenuItem())

        close_pm_item = Gtk.MenuItem.new_with_mnemonic("_Close Private Message")
        close_pm_item.connect("activate", self.on_close_pm)
        channel_menu.append(close_pm_item)

        menubar.append(channel_item)

        # Settings menu
        settings_menu = Gtk.Menu()
        settings_item = Gtk.MenuItem.new_with_mnemonic("Se_ttings")
        settings_item.set_submenu(settings_menu)

        preferences_item = Gtk.MenuItem.new_with_mnemonic("_Preferences...")
        preferences_item.connect("activate", self.on_preferences)
        settings_menu.append(preferences_item)

        menubar.append(settings_item)

        # Help menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem.new_with_mnemonic("_Help")
        help_item.set_submenu(help_menu)

        about_item = Gtk.MenuItem.new_with_mnemonic("_About")
        about_item.connect("activate", self.on_about)
        help_menu.append(about_item)

        menubar.append(help_item)

        return menubar

    def _create_left_panel(self) -> Gtk.Box:
        """Create left panel with server/channel list"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Label for the tree view
        label = Gtk.Label(label="Servers and Channels")
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        # ScrolledWindow for tree view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scrolled, True, True, 0)

        # TreeView for servers and channels
        self.tree_store = Gtk.TreeStore(str, str)  # Display name, identifier
        self.tree_view = Gtk.TreeView(model=self.tree_store)
        self.tree_view.set_headers_visible(False)

        # Set accessible properties for screen readers
        accessible = self.tree_view.get_accessible()
        if accessible:
            accessible.set_name("Servers and Channels")

            # Link the label to the tree view using ATK relations
            try:
                from gi.repository import Atk
                label_accessible = label.get_accessible()
                if label_accessible:
                    relation_set = accessible.ref_relation_set()
                    relation = Atk.Relation.new(
                        [label_accessible],
                        Atk.RelationType.LABELLED_BY
                    )
                    relation_set.add(relation)
            except Exception:
                pass  # ATK relations not critical, continue without them

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Name", renderer, text=0)
        self.tree_view.append_column(column)

        # Handle selection
        select = self.tree_view.get_selection()
        select.connect("changed", self.on_tree_selection_changed)

        # Handle context menu on tree items
        self.tree_view.connect("button-press-event", self.on_tree_button_press)
        self.tree_view.connect("key-press-event", self.on_tree_key_press)

        scrolled.add(self.tree_view)

        return box

    def _create_right_panel(self) -> Gtk.Box:
        """Create right panel with chat display, users list, and input"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Current channel/server label
        self.channel_label = Gtk.Label(label="No channel selected")
        self.channel_label.set_halign(Gtk.Align.START)
        box.pack_start(self.channel_label, False, False, 0)

        # Horizontal paned layout for chat area and users list
        self.h_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.h_paned.set_visible(True)
        self.h_paned.show()
        # Set position later after window is realized to ensure both panels are visible
        box.pack_start(self.h_paned, True, True, 0)

        # Left side of paned: Chat area
        chat_scrolled = Gtk.ScrolledWindow()
        chat_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        chat_scrolled.set_hexpand(True)
        chat_scrolled.set_vexpand(True)
        # Don't set min_content_width - let paned positioning handle sizing
        self.h_paned.add1(chat_scrolled)

        # TextView for messages (read-only but navigable)
        self.message_view = Gtk.TextView()
        self.message_view.set_editable(False)
        self.message_view.set_cursor_visible(True)
        self.message_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.message_view.set_left_margin(6)
        self.message_view.set_right_margin(6)
        # Ensure it can receive focus for keyboard navigation
        self.message_view.set_can_focus(True)

        # Set monospace font for better readability
        font_desc = Pango.FontDescription("monospace 10")
        self.message_view.modify_font(font_desc)

        chat_scrolled.add(self.message_view)

        # Store scrolled window reference for auto-scrolling
        self.message_scrolled = chat_scrolled

        # Right side of paned: Users list
        users_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        users_box.show()
        self.h_paned.add2(users_box)

        # Label for users list (with mnemonic for accessibility)
        users_label = Gtk.Label.new_with_mnemonic("_Users")
        users_label.set_halign(Gtk.Align.START)
        users_label.show()
        users_box.pack_start(users_label, False, False, 0)

        # ScrolledWindow for users list
        users_scrolled = Gtk.ScrolledWindow()
        users_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        # Don't set min_content_width - let paned positioning handle sizing
        users_scrolled.show()
        users_box.pack_start(users_scrolled, True, True, 0)

        # ListBox for users (simpler than TreeView for a flat list)
        self.users_list = Gtk.ListBox()
        self.users_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        # Allow focus so it's in the tab chain
        self.users_list.set_can_focus(True)
        self.users_list.set_visible(True)
        self.users_list.show()

        # Set accessible properties for screen readers
        accessible = self.users_list.get_accessible()
        if accessible:
            accessible.set_name("Channel Users List")
            accessible.set_description("List of users currently in the channel")

        # Set the mnemonic widget for keyboard accessibility
        users_label.set_mnemonic_widget(self.users_list)

        # Add a placeholder so the list is always visible even when empty
        placeholder = Gtk.Label(label="No users")
        placeholder.get_style_context().add_class("dim-label")
        self.users_list.set_placeholder(placeholder)
        placeholder.show()

        # Connect events
        self.users_list.connect("button-press-event", self.on_users_list_button_press)
        self.users_list.connect("key-press-event", self.on_users_list_key_press)
        self.users_list.connect("row-activated", self.on_users_list_row_activated)

        users_scrolled.add(self.users_list)

        # Message input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Label for input field (with mnemonic for accessibility)
        input_label = Gtk.Label.new_with_mnemonic("_Message:")
        input_box.pack_start(input_label, False, False, 0)

        # ScrolledWindow for message input (to support multi-line and spell checking)
        message_scrolled = Gtk.ScrolledWindow()
        message_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        message_scrolled.set_min_content_height(60)  # Small height for ~2-3 lines
        message_scrolled.set_max_content_height(120)  # Limit max height to ~4-5 lines

        # TextView for message input (supports spell checking)
        self.message_entry = Gtk.TextView()
        self.message_entry.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.message_entry.set_left_margin(6)
        self.message_entry.set_right_margin(6)
        self.message_entry.set_top_margin(3)
        self.message_entry.set_bottom_margin(3)
        self.message_entry.set_accepts_tab(False)  # Tab should move focus/complete, not insert tab

        # Set monospace font to match message view
        font_desc = Pango.FontDescription("monospace 10")
        self.message_entry.modify_font(font_desc)

        # Add spell checking if available
        if GSPELL_AVAILABLE:
            try:
                # Get the default language
                language = Gspell.Language.get_default()
                if language is None:
                    # Fallback to English if no default language
                    language = Gspell.Language.lookup("en_US")

                if language is not None:
                    # Create checker with the language
                    checker = Gspell.Checker.new(language)

                    # Get the text buffer and wrap it with Gspell
                    text_buffer = self.message_entry.get_buffer()
                    gspell_buffer = Gspell.TextBuffer.get_from_gtk_text_buffer(text_buffer)
                    gspell_buffer.set_spell_checker(checker)

                    # Get the text view and wrap it with Gspell
                    gspell_view = Gspell.TextView.get_from_gtk_text_view(self.message_entry)
                    gspell_view.set_inline_spell_checking(True)
                    gspell_view.set_enable_language_menu(True)
                else:
                    print("Warning: No spell checking language available")
            except Exception as e:
                print(f"Warning: Failed to enable spell checking: {e}")

        self.message_entry.connect("key-press-event", self.on_message_entry_key_press)
        input_label.set_mnemonic_widget(self.message_entry)
        message_scrolled.add(self.message_entry)
        input_box.pack_start(message_scrolled, True, True, 0)

        # Send button
        send_button = Gtk.Button(label="Send")
        send_button.connect("clicked", self.on_send_message)
        input_box.pack_start(send_button, False, False, 0)

        box.pack_start(input_box, False, False, 0)

        # Set focus chain on h_paned to control order of chat vs users
        # Order: chat_scrolled → users_scrolled
        self.h_paned.set_focus_chain([chat_scrolled, users_scrolled])

        return box

    def _on_window_realized(self, widget) -> None:
        """Set paned positions after window is realized and sized"""
        # Use idle_add to ensure layout is complete before setting positions
        GLib.idle_add(self._set_paned_positions)

    def _on_window_size_allocate(self, widget, allocation) -> None:
        """Update paned positions when window is resized"""
        # Only update if the window is actually visible and realized
        # This prevents unnecessary updates during initial window construction
        if self.get_realized() and self.get_visible():
            self._update_paned_positions()

    def _set_paned_positions(self) -> bool:
        """Set paned positions based on window size (called once on realize)"""
        self._update_paned_positions()
        return False  # Don't repeat

    def _update_paned_positions(self) -> None:
        """Update paned positions based on current window size"""
        # Set main paned position (left panel vs right panel)
        if self.main_paned:
            self.main_paned.set_position(self.LEFT_PANEL_WIDTH)

        # Set h_paned position (chat area vs users list)
        if self.h_paned:
            # Get the actual window width
            window_width = self.get_size()[0]

            # Calculate available width for h_paned
            # Account for left panel + borders + spacing
            available_width = window_width - self.LEFT_PANEL_WITH_BORDERS

            # Give users list fixed width, rest to chat
            # This ensures users list is always visible
            users_width = self.USERS_LIST_WIDTH
            position = max(available_width - users_width, available_width // 2)

            self.h_paned.set_position(position)

    def set_managers(self, irc_manager, sound_manager, config_manager, log_manager=None) -> None:
        """
        Set manager references

        Args:
            irc_manager: IRCManager instance
            sound_manager: SoundManager instance
            config_manager: ConfigManager instance
            log_manager: LogManager instance (optional)
        """
        self.irc_manager = irc_manager
        self.sound_manager = sound_manager
        self.config_manager = config_manager
        self.log_manager = log_manager

    def announce_to_screen_reader(self, message: str) -> None:
        """
        Send announcement to screen reader via AT-SPI2

        Args:
            message: Message to announce
        """
        try:
            # Get accessible object from main window
            atk_object = self.get_accessible()

            if not atk_object:
                print("Warning: No accessible object available for announcement")
                return

            # Emit announcement signal for screen readers
            # This signal will be picked up by Orca and read aloud
            atk_object.emit("announcement", message)
        except Exception as e:
            # Fallback to notification signal
            print(f"Warning: Failed to emit 'announcement' signal: {e}")
            try:
                atk_object = self.get_accessible()
                if atk_object:
                    atk_object.emit("notification", message)
            except Exception as e2:
                print(f"Error: Failed to emit accessibility announcement: {e2}")

    def toggle_announcement_mode(self) -> None:
        """
        Toggle between announcement modes: all messages -> mentions only -> none -> all messages
        This is a temporary toggle that doesn't save to config
        """
        # Determine current mode (either from temp override or from config)
        if self.temp_announcement_mode is None:
            # Using config settings - determine what mode we're in
            if self.config_manager.should_announce_all_messages():
                current_mode = "all"
            elif self.config_manager.should_announce_mentions():
                current_mode = "mentions"
            else:
                current_mode = "none"
        else:
            current_mode = self.temp_announcement_mode

        # Cycle to next mode
        if current_mode == "all":
            self.temp_announcement_mode = "mentions"
            announcement = "Announcing mentions only"
        elif current_mode == "mentions":
            self.temp_announcement_mode = "none"
            announcement = "Announcements disabled"
        else:  # none
            self.temp_announcement_mode = "all"
            announcement = "Announcing all messages"

        # Announce the new mode
        self.announce_to_screen_reader(announcement)

    def toggle_channel_announcement_mode(self) -> None:
        """
        Toggle announcements for the current channel/PM only (F2).
        Cycles: enabled -> disabled -> unset (falls back to Ctrl+S/config)
        """
        if not self.current_server or not self.current_target:
            self.announce_to_screen_reader("No channel selected")
            return

        # Don't allow toggling for server buffers or mentions
        if self.current_target == self.current_server or self.current_target == "mentions":
            self.announce_to_screen_reader("Cannot toggle announcements for this buffer")
            return

        key = (self.current_server, self.current_target)
        current = self.channel_announcement_overrides.get(key)

        # Cycle: None (unset) -> True (enabled) -> False (disabled) -> None
        if current is None:
            self.channel_announcement_overrides[key] = True
            announcement = f"Announcements enabled for {self.current_target}"
        elif current is True:
            self.channel_announcement_overrides[key] = False
            announcement = f"Announcements disabled for {self.current_target}"
        else:  # False
            # Remove from dict to fall back to global setting
            del self.channel_announcement_overrides[key]
            announcement = f"Announcements for {self.current_target} using global setting"

        self.announce_to_screen_reader(announcement)

    def _should_announce_for_channel(self, server: str, target: str) -> Optional[bool]:
        """
        Check if there's a per-channel override for announcements.

        Returns:
            True if channel override enables announcements
            False if channel override disables announcements
            None if no override (should fall back to global settings)
        """
        key = (server, target)
        return self.channel_announcement_overrides.get(key)

    def should_announce_all_messages(self, server: Optional[str] = None, target: Optional[str] = None) -> bool:
        """
        Check if all messages should be announced.

        Priority: per-channel override (F2) -> session toggle (Ctrl+S) -> config

        Args:
            server: Server name (optional, for per-channel check)
            target: Channel or PM target (optional, for per-channel check)
        """
        # Check per-channel override first (F2 toggle)
        if server and target:
            channel_override = self._should_announce_for_channel(server, target)
            if channel_override is not None:
                return channel_override

        # Fall back to session toggle (Ctrl+S)
        if self.temp_announcement_mode is not None:
            return self.temp_announcement_mode == "all"

        # Fall back to config
        return self.config_manager.should_announce_all_messages() if self.config_manager else False

    def should_announce_mentions(self, server: Optional[str] = None, target: Optional[str] = None) -> bool:
        """
        Check if mentions should be announced.

        Priority: per-channel override (F2) -> session toggle (Ctrl+S) -> config

        Args:
            server: Server name (optional, for per-channel check)
            target: Channel or PM target (optional, for per-channel check)
        """
        # Check per-channel override first (F2 toggle)
        if server and target:
            channel_override = self._should_announce_for_channel(server, target)
            if channel_override is not None:
                return channel_override

        # Fall back to session toggle (Ctrl+S)
        if self.temp_announcement_mode is not None:
            return self.temp_announcement_mode in ("all", "mentions")

        # Fall back to config
        # Mentions should be announced if EITHER:
        # 1. "Announce mentions only" is enabled, OR
        # 2. "Announce all messages" is enabled (which includes mentions)
        if self.config_manager:
            announce_all = self.config_manager.should_announce_all_messages()
            announce_mentions = self.config_manager.should_announce_mentions()
            return announce_all or announce_mentions

        return False

    # Buffer trim threshold: only trim when this percentage over the limit
    # This reduces the frequency of trimming operations for better performance
    BUFFER_TRIM_THRESHOLD = 1.1  # 10% over limit

    def _trim_buffer(self, buffer: Gtk.TextBuffer) -> None:
        """
        Trim buffer to scrollback limit if necessary

        Only trims when buffer exceeds the limit by 10% (BUFFER_TRIM_THRESHOLD)
        to reduce the frequency of trimming operations.

        Args:
            buffer: TextBuffer to trim
        """
        if not self.config_manager:
            return

        limit = self.config_manager.get_scrollback_limit()
        if limit == 0:  # 0 = unlimited
            return

        # Get line count
        line_count = buffer.get_line_count()

        # Only trim if we're more than 10% over the limit
        # This reduces trim frequency for better performance
        trim_threshold = int(limit * self.BUFFER_TRIM_THRESHOLD)
        if line_count > trim_threshold:
            lines_to_delete = line_count - limit

            # Get iterator at start of buffer
            start_iter = buffer.get_start_iter()

            # Move iterator to end of lines to delete
            end_iter = buffer.get_iter_at_line(lines_to_delete)

            # Delete the lines
            buffer.delete(start_iter, end_iter)

    def add_message(self, server: str, target: str, sender: str, message: str,
                   is_mention: bool = False, is_system: bool = False) -> None:
        """
        Add message to chat display

        Args:
            server: Server name
            target: Channel or PM recipient
            sender: Message sender
            message: Message text
            is_mention: Whether user is mentioned
            is_system: Whether it's a system message
        """
        # Get or create buffer for this server/target
        key = (server, target)
        if key not in self.message_buffers:
            self.message_buffers[key] = Gtk.TextBuffer()

        buffer = self.message_buffers[key]

        # Format message with timestamp (if enabled)
        if self.config_manager.should_show_timestamps():
            timestamp = datetime.now().strftime("%H:%M:%S")
            if is_system:
                formatted = f"[{timestamp}] * {message}\n"
            else:
                formatted = f"[{timestamp}] <{sender}> {message}\n"
        else:
            if is_system:
                formatted = f"* {message}\n"
            else:
                formatted = f"<{sender}> {message}\n"

        # Add to buffer at the end (not at cursor position)
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, formatted)

        # Trim buffer if it exceeds scrollback limit
        self._trim_buffer(buffer)

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Handle announcements and sounds
        if is_mention:
            # Add to mentions buffer if this is a channel mention (not PM)
            if target.startswith("#"):
                self.add_message_to_mentions_buffer(server, target, sender, message)

            # Announce mention to screen reader (if mentions OR all messages is enabled)
            if self.should_announce_mentions(server, target):
                self.announce_to_screen_reader(f"{sender} mentioned you in {target}: {message}")

            # Play mention sound
            if self.sound_manager:
                self.sound_manager.play_mention()

        elif not is_system:
            # Regular message
            if self.should_announce_all_messages(server, target):
                self.announce_to_screen_reader(f"{sender} in {target}: {message}")

            # Play appropriate sound (PM sound for private messages, message sound for channels)
            if self.sound_manager:
                if not target.startswith("#"):
                    self.sound_manager.play_privmsg()
                else:
                    self.sound_manager.play_message()

    def add_system_message(self, server: str, target: str, message: str, announce: bool = False) -> None:
        """
        Add system message

        Args:
            server: Server name
            target: Channel or server
            message: System message
            announce: Whether to announce this message to screen readers
        """
        self.add_message(server, target, "", message, is_system=True)

        # Announce to screen reader if requested
        if announce:
            self.announce_to_screen_reader(message)

    def add_action_message(self, server: str, target: str, sender: str, action: str, is_mention: bool = False) -> None:
        """
        Add CTCP ACTION message (/me)

        Args:
            server: Server name
            target: Channel or PM recipient
            sender: User performing the action
            action: Action text
            is_mention: Whether the user is mentioned in this action
        """
        # Get or create buffer for this server/target
        key = (server, target)
        if key not in self.message_buffers:
            self.message_buffers[key] = Gtk.TextBuffer()

        buffer = self.message_buffers[key]

        # Format action message with timestamp (if enabled)
        if self.config_manager.should_show_timestamps():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] * {sender} {action}\n"
        else:
            formatted = f"* {sender} {action}\n"

        # Add to buffer at the end
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, formatted)

        # Trim buffer if it exceeds scrollback limit
        self._trim_buffer(buffer)

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Handle mentions
        if is_mention:
            # Add to mentions buffer if this is a channel mention (not PM)
            if target.startswith("#"):
                # Add action to mentions buffer
                mentions_iter = self._get_or_create_mentions_buffer(server)
                if mentions_iter:
                    key = (server, "mentions")
                    if key not in self.message_buffers:
                        self.message_buffers[key] = Gtk.TextBuffer()
                    mentions_buffer = self.message_buffers[key]

                    # Format with channel prefix
                    if self.config_manager.should_show_timestamps():
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        mentions_formatted = f"[{timestamp}] {target}: * {sender} {action}\n"
                    else:
                        mentions_formatted = f"{target}: * {sender} {action}\n"

                    end_iter = mentions_buffer.get_end_iter()
                    mentions_buffer.insert(end_iter, mentions_formatted)

                    # Trim buffer if it exceeds scrollback limit
                    self._trim_buffer(mentions_buffer)

                    # Update view if mentions buffer is visible
                    if self.current_server == server and self.current_target == "mentions":
                        self.message_view.set_buffer(mentions_buffer)
                        self._scroll_to_bottom()

            # Announce mention to screen reader
            if self.should_announce_mentions(server, target):
                self.announce_to_screen_reader(f"{sender} {action}")
        else:
            # Regular action (not a mention)
            if self.should_announce_all_messages(server, target):
                self.announce_to_screen_reader(f"{sender} {action}")

        # Note: Sound is played in __main__.py to avoid duplicates

    def add_notice_message(self, server: str, target: str, sender: str, message: str) -> None:
        """
        Add NOTICE message

        Args:
            server: Server name
            target: Channel or PM recipient
            sender: Notice sender
            message: Notice text
        """
        # Get or create buffer for this server/target
        key = (server, target)
        if key not in self.message_buffers:
            self.message_buffers[key] = Gtk.TextBuffer()

        buffer = self.message_buffers[key]

        # Format notice message with timestamp (if enabled)
        if self.config_manager.should_show_timestamps():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] -{sender}- {message}\n"
        else:
            formatted = f"-{sender}- {message}\n"

        # Add to buffer at the end
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, formatted)

        # Trim buffer if it exceeds scrollback limit
        self._trim_buffer(buffer)

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Announce to screen reader if configured
        if self.should_announce_all_messages(server, target):
            self.announce_to_screen_reader(f"Notice from {sender}: {message}")

        # Play notice sound
        if self.sound_manager:
            self.sound_manager.play_notice()

    def add_message_to_mentions_buffer(self, server: str, channel: str, sender: str, message: str) -> None:
        """
        Add message to mentions buffer (without AT-SPI announcement to avoid duplicates)

        Args:
            server: Server name
            channel: Channel where mention occurred
            sender: Message sender
            message: Message text
        """
        # Get or create the mentions buffer for this server
        mentions_iter = self._get_or_create_mentions_buffer(server)
        if not mentions_iter:
            return

        # Get or create buffer for mentions
        key = (server, "mentions")
        if key not in self.message_buffers:
            self.message_buffers[key] = Gtk.TextBuffer()

        buffer = self.message_buffers[key]

        # Format message with timestamp and channel prefix
        if self.config_manager.should_show_timestamps():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] {channel}: <{sender}> {message}\n"
        else:
            formatted = f"{channel}: <{sender}> {message}\n"

        # Add to buffer at the end
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, formatted)

        # Trim buffer if it exceeds scrollback limit
        self._trim_buffer(buffer)

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == "mentions":
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # NOTE: No AT-SPI announcements or sounds here to avoid duplicates

    def update_users_list(self, server: str = None, channel: str = None) -> None:
        """
        Update users list for current or specified channel

        Args:
            server: Server name (uses current if None)
            channel: Channel name (uses current if None)
        """
        # Use current context if not specified
        if server is None:
            server = self.current_server
        if channel is None:
            channel = self.current_target

        # Clear current users list
        for child in self.users_list.get_children():
            self.users_list.remove(child)

        # Only show users for channels (not PMs or server views)
        if server and channel and channel.startswith("#") and self.irc_manager:
            users = self.irc_manager.get_channel_users(server, channel)
            for user in users:
                label = Gtk.Label(label=user, xalign=0)
                label.set_margin_start(6)
                label.set_margin_end(6)
                label.set_margin_top(3)
                label.set_margin_bottom(3)
                self.users_list.add(label)

            # Show all the new labels
            self.users_list.show_all()

    def _scroll_to_bottom(self) -> None:
        """Scroll message view to bottom"""
        adj = self.message_scrolled.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())

    def add_server_to_tree(self, server_name: str) -> Gtk.TreeIter:
        """
        Add server to tree view

        Args:
            server_name: Name of server

        Returns:
            TreeIter for the server
        """
        return self.tree_store.append(None, [server_name, f"server:{server_name}"])

    def add_channel_to_tree(self, server_iter: Gtk.TreeIter, channel: str) -> Gtk.TreeIter:
        """
        Add channel to tree view under server

        Args:
            server_iter: TreeIter of parent server
            channel: Channel name

        Returns:
            TreeIter for the channel (existing or newly created)
        """
        server_name = self.tree_store.get_value(server_iter, 0)
        expected_id = f"channel:{server_name}:{channel}"

        # Check if channel already exists under this server
        child_iter = self.tree_store.iter_children(server_iter)
        while child_iter:
            if self.tree_store.get_value(child_iter, 1) == expected_id:
                return child_iter  # Already exists, return existing iter
            child_iter = self.tree_store.iter_next(child_iter)

        return self.tree_store.append(server_iter, [channel, expected_id])

    def remove_channel_from_tree(self, server_name: str, channel: str) -> None:
        """
        Remove channel from tree view

        Args:
            server_name: Name of server
            channel: Channel name to remove
        """
        # Find the server node
        iter = self.tree_store.get_iter_first()
        while iter:
            if self.tree_store.get_value(iter, 0) == server_name:
                # Found server, now find channel among its children
                child_iter = self.tree_store.iter_children(iter)
                while child_iter:
                    identifier = self.tree_store.get_value(child_iter, 1)
                    if identifier == f"channel:{server_name}:{channel}":
                        # If we're viewing this channel, navigate to previous buffer
                        if self.current_server == server_name and self.current_target == channel:
                            closed_identifier = f"channel:{server_name}:{channel}"

                            # Get identifier of previous buffer BEFORE removal
                            prev_identifier = self._get_previous_buffer_identifier(server_name, closed_identifier)

                            # Remove the channel from tree
                            self.tree_store.remove(child_iter)

                            # Navigate to previous buffer by identifier
                            self._navigate_to_identifier(prev_identifier)
                        else:
                            self.tree_store.remove(child_iter)
                        return
                    child_iter = self.tree_store.iter_next(child_iter)
                return
            iter = self.tree_store.iter_next(iter)

    def remove_server_from_tree(self, server_name: str) -> None:
        """
        Remove server from tree view

        Args:
            server_name: Name of server to remove
        """
        iter = self.tree_store.get_iter_first()
        while iter:
            if self.tree_store.get_value(iter, 0) == server_name:
                self.tree_store.remove(iter)
                # Clean up PM tracking for this server
                if server_name in self.pm_iters:
                    del self.pm_iters[server_name]
                if server_name in self.pm_folder_iters:
                    del self.pm_folder_iters[server_name]
                # Clean up mentions tracking for this server
                if server_name in self.mentions_iters:
                    del self.mentions_iters[server_name]
                # Reset title if we were viewing this server
                if self.current_server == server_name:
                    self.current_server = None
                    self.current_target = None
                    self._update_window_title()
                break
            iter = self.tree_store.iter_next(iter)

    def _get_or_create_pm_folder(self, server_name: str) -> Gtk.TreeIter:
        """
        Get or create the "Private Messages" folder for a server

        Args:
            server_name: Name of server

        Returns:
            TreeIter for the PM folder
        """
        # Return existing folder if it exists
        if server_name in self.pm_folder_iters:
            return self.pm_folder_iters[server_name]

        # Find the server's tree iter
        server_iter = None
        iter = self.tree_store.get_iter_first()
        while iter:
            if self.tree_store.get_value(iter, 0) == server_name:
                server_iter = iter
                break
            iter = self.tree_store.iter_next(iter)

        if not server_iter:
            return None

        # Create "Private Messages" folder under the server
        pm_folder_iter = self.tree_store.append(
            server_iter,
            ["Private Messages", f"pm_folder:{server_name}"]
        )
        self.pm_folder_iters[server_name] = pm_folder_iter

        # Initialize PM tracking dict for this server
        if server_name not in self.pm_iters:
            self.pm_iters[server_name] = {}

        return pm_folder_iter

    def _get_or_create_mentions_buffer(self, server_name: str) -> Gtk.TreeIter:
        """
        Get or create the "Mentions" buffer for a server

        Args:
            server_name: Name of server

        Returns:
            TreeIter for the mentions buffer
        """
        # Return existing buffer if it exists
        if server_name in self.mentions_iters:
            return self.mentions_iters[server_name]

        # Find the server's tree iter
        server_iter = None
        iter = self.tree_store.get_iter_first()
        while iter:
            if self.tree_store.get_value(iter, 0) == server_name:
                server_iter = iter
                break
            iter = self.tree_store.iter_next(iter)

        if not server_iter:
            return None

        # Create "Mentions" buffer under the server
        mentions_iter = self.tree_store.append(
            server_iter,
            ["Mentions", f"mentions:{server_name}"]
        )
        self.mentions_iters[server_name] = mentions_iter

        return mentions_iter

    def add_pm_to_tree(self, server_name: str, username: str) -> Gtk.TreeIter:
        """
        Add private message conversation to tree

        Args:
            server_name: Name of server
            username: Username for PM

        Returns:
            TreeIter for the PM entry
        """
        # Check if PM already exists
        if server_name in self.pm_iters and username in self.pm_iters[server_name]:
            return self.pm_iters[server_name][username]

        # Get or create PM folder
        pm_folder_iter = self._get_or_create_pm_folder(server_name)
        if not pm_folder_iter:
            return None

        # Add PM under the folder
        pm_iter = self.tree_store.append(
            pm_folder_iter,
            [username, f"pm:{server_name}:{username}"]
        )

        # Track it
        if server_name not in self.pm_iters:
            self.pm_iters[server_name] = {}
        self.pm_iters[server_name][username] = pm_iter

        # Expand the PM folder so the new PM is visible
        path = self.tree_store.get_path(pm_folder_iter)
        self.tree_view.expand_row(path, False)

        return pm_iter

    def remove_pm_from_tree(self, server_name: str, username: str) -> None:
        """
        Remove private message conversation from tree

        Args:
            server_name: Name of server
            username: Username for PM
        """
        if server_name in self.pm_iters and username in self.pm_iters[server_name]:
            pm_iter = self.pm_iters[server_name][username]
            self.tree_store.remove(pm_iter)
            del self.pm_iters[server_name][username]

            # If no more PMs, remove the folder
            if not self.pm_iters[server_name]:
                if server_name in self.pm_folder_iters:
                    self.tree_store.remove(self.pm_folder_iters[server_name])
                    del self.pm_folder_iters[server_name]
                del self.pm_iters[server_name]

    def update_status(self, message: str) -> None:
        """
        Update status bar

        Args:
            message: Status message
        """
        self.statusbar.pop(self.statusbar_context)
        self.statusbar.push(self.statusbar_context, message)

    # Event handlers
    def on_tree_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        """Handle tree view selection change"""
        model, iter = selection.get_selected()
        if iter:
            identifier = model.get_value(iter, 1)

            if identifier.startswith("server:"):
                # Server selected
                server_name = identifier.split(":", 1)[1]
                self.current_server = server_name
                self.current_target = server_name  # Use server as target for server messages
                self.channel_label.set_text(f"Server: {server_name}")

            elif identifier.startswith("channel:"):
                # Channel selected
                parts = identifier.split(":", 2)
                server_name = parts[1]
                channel = parts[2]
                self.current_server = server_name
                self.current_target = channel
                self.channel_label.set_text(f"{server_name} / {channel}")

            elif identifier.startswith("pm:"):
                # Private message selected
                parts = identifier.split(":", 2)
                server_name = parts[1]
                username = parts[2]
                self.current_server = server_name
                self.current_target = username
                self.channel_label.set_text(f"{server_name} / PM: {username}")

            elif identifier.startswith("pm_folder:"):
                # PM folder selected (just show a message)
                server_name = identifier.split(":", 1)[1]
                self.current_server = server_name
                self.current_target = None
                self.channel_label.set_text(f"{server_name} / Private Messages")

            elif identifier.startswith("mentions:"):
                # Mentions buffer selected
                server_name = identifier.split(":", 1)[1]
                self.current_server = server_name
                self.current_target = "mentions"
                self.channel_label.set_text(f"{server_name} / Mentions")

            # Load message buffer for this context
            key = (self.current_server, self.current_target)
            if key in self.message_buffers:
                self.message_view.set_buffer(self.message_buffers[key])
            else:
                # Create new buffer
                self.message_buffers[key] = Gtk.TextBuffer()
                self.message_view.set_buffer(self.message_buffers[key])

            # Update users list for the selected channel
            self.update_users_list()

            self._scroll_to_bottom()

            # Update window title to reflect current view
            self._update_window_title()

    def _update_window_title(self) -> None:
        """Update window title based on current server and target"""
        if not self.current_server:
            # No server selected
            self.set_title(self.app_title)
        elif not self.current_target or self.current_target == self.current_server:
            # Server view (no specific channel/PM)
            self.set_title(f"{self.current_server} - {self.app_title}")
        elif self.current_target == "mentions":
            # Mentions buffer
            self.set_title(f"Mentions - {self.current_server} - {self.app_title}")
        elif self.current_target.startswith("#"):
            # Channel
            self.set_title(f"{self.current_target} - {self.current_server} - {self.app_title}")
        else:
            # Private message
            self.set_title(f"PM: {self.current_target} - {self.current_server} - {self.app_title}")

    def on_window_key_press(self, widget, event) -> bool:
        """Handle window-level keyboard shortcuts"""
        # Ctrl+W - Close current PM, mentions buffer, or leave channel
        if event.keyval == Gdk.KEY_w and event.state & Gdk.ModifierType.CONTROL_MASK:
            if self.current_target == "mentions":
                # It's a mentions buffer - close it
                self.on_close_mentions(None)
                return True
            elif self.current_target and not self.current_target.startswith("#") and self.current_target != self.current_server:
                # It's a PM - close it
                self.on_close_pm(None)
                return True
            elif self.current_target and self.current_target.startswith("#"):
                # It's a channel - leave it
                self.on_part_channel(None)
                return True

        # Ctrl+S - Toggle announcement mode
        if event.keyval == Gdk.KEY_s and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.toggle_announcement_mode()
            return True

        # F2 - Toggle announcements for current channel only
        if event.keyval == Gdk.KEY_F2:
            self.toggle_channel_announcement_mode()
            return True

        # Ctrl+PageDown - Cycle to next buffer
        if event.keyval == Gdk.KEY_Page_Down and event.state & Gdk.ModifierType.CONTROL_MASK:
            self._cycle_buffer(forward=True)
            return True

        # Ctrl+PageUp - Cycle to previous buffer
        if event.keyval == Gdk.KEY_Page_Up and event.state & Gdk.ModifierType.CONTROL_MASK:
            self._cycle_buffer(forward=False)
            return True

        return False

    def _get_flat_tree_items(self) -> list:
        """
        Get a flat list of all tree items in display order.

        Returns list of tuples: (path, identifier, display_name, server_name)
        Excludes PM folders (pm_folder:) as they're just containers.
        """
        items = []

        def traverse(iter, parent_path=None):
            while iter:
                path = self.tree_store.get_path(iter)
                display_name = self.tree_store.get_value(iter, 0)
                identifier = self.tree_store.get_value(iter, 1)

                # Skip PM folders - they're just containers
                if not identifier.startswith("pm_folder:"):
                    # Determine server name from identifier
                    if identifier.startswith("server:"):
                        server_name = identifier.split(":", 1)[1]
                    elif identifier.startswith("channel:") or identifier.startswith("pm:") or identifier.startswith("mentions:"):
                        server_name = identifier.split(":", 2)[1]
                    else:
                        server_name = ""

                    items.append((path, identifier, display_name, server_name))

                # Traverse children
                child_iter = self.tree_store.iter_children(iter)
                if child_iter:
                    traverse(child_iter, path)

                iter = self.tree_store.iter_next(iter)

        root_iter = self.tree_store.get_iter_first()
        if root_iter:
            traverse(root_iter)

        return items

    def _get_current_tree_index(self, items: list) -> int:
        """
        Find the index of the currently selected item in the flat list.

        Returns -1 if no item is selected or not found.
        """
        if not self.current_server:
            return -1

        # Build the identifier for current selection
        if not self.current_target or self.current_target == self.current_server:
            current_id = f"server:{self.current_server}"
        elif self.current_target == "mentions":
            current_id = f"mentions:{self.current_server}"
        elif self.current_target.startswith("#"):
            current_id = f"channel:{self.current_server}:{self.current_target}"
        else:
            current_id = f"pm:{self.current_server}:{self.current_target}"

        for i, (path, identifier, display_name, server_name) in enumerate(items):
            if identifier == current_id:
                return i

        return -1

    def _cycle_buffer(self, forward: bool = True) -> None:
        """
        Cycle to next or previous buffer in the tree.

        Args:
            forward: True for next (Ctrl+PageDown), False for previous (Ctrl+PageUp)
        """
        items = self._get_flat_tree_items()
        if not items:
            return

        current_index = self._get_current_tree_index(items)

        # Calculate new index with wrapping
        if current_index == -1:
            # No current selection, start at beginning or end
            new_index = 0 if forward else len(items) - 1
        else:
            if forward:
                new_index = (current_index + 1) % len(items)
            else:
                new_index = (current_index - 1) % len(items)

        # Get the new item
        path, identifier, display_name, server_name = items[new_index]

        # Expand parent if needed (for channels, PMs, mentions under a server)
        if path.get_depth() > 1:
            parent_path = path.copy()
            parent_path.up()
            self.tree_view.expand_to_path(path)

        # Set cursor (this will trigger on_tree_selection_changed)
        self.tree_view.set_cursor(path, None, False)

    def _get_previous_buffer_identifier(self, server_name: str, current_identifier: str) -> str:
        """
        Get the identifier of the previous buffer in the same server.

        Args:
            server_name: The server to search within
            current_identifier: The identifier of the buffer being closed

        Returns:
            Identifier of the previous buffer, or server identifier if at first item
        """
        items = self._get_flat_tree_items()

        # Filter to only items in this server
        server_items = [(path, ident, name, srv) for path, ident, name, srv in items
                        if srv == server_name]

        if not server_items:
            return f"server:{server_name}"

        # Find the current item's index
        current_index = -1
        for i, (path, ident, name, srv) in enumerate(server_items):
            if ident == current_identifier:
                current_index = i
                break

        if current_index == -1:
            return f"server:{server_name}"

        # Return the identifier of the previous item
        if current_index > 1:
            # Go to previous non-server item
            return server_items[current_index - 1][1]
        else:
            # We're at the first item or server, go to server
            return server_items[0][1]

    def _navigate_to_identifier(self, target_identifier: str) -> None:
        """
        Navigate to a buffer by its identifier.

        Args:
            target_identifier: The identifier to navigate to
        """
        items = self._get_flat_tree_items()

        for path, ident, name, srv in items:
            if ident == target_identifier:
                # Expand if needed and set cursor
                if path.get_depth() > 1:
                    self.tree_view.expand_to_path(path)
                self.tree_view.set_cursor(path, None, False)
                return

    def on_tree_button_press(self, widget, event) -> bool:
        """Handle button press on tree view (for context menu)"""
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:  # Right-click
            # Get the clicked item
            path_info = self.tree_view.get_path_at_pos(int(event.x), int(event.y))
            if path_info:
                path = path_info[0]
                self.tree_view.set_cursor(path)

                # Get the identifier
                model = self.tree_view.get_model()
                iter = model.get_iter(path)
                identifier = model.get_value(iter, 1)

                self._show_tree_context_menu(identifier, event)
                return True
        return False

    def on_tree_key_press(self, widget, event) -> bool:
        """Handle key press on tree view (for Menu key)"""
        if event.keyval == Gdk.KEY_Menu or \
           (event.keyval == Gdk.KEY_F10 and event.state & Gdk.ModifierType.SHIFT_MASK):
            # Get the selected item
            selection = self.tree_view.get_selection()
            model, iter = selection.get_selected()
            if iter:
                identifier = model.get_value(iter, 1)
                self._show_tree_context_menu(identifier, event.time)
                return True
        return False

    def _show_tree_context_menu(self, identifier: str, event_or_time):
        """Show context menu for tree item"""
        menu = Gtk.Menu()

        if identifier.startswith("pm:"):
            # PM context menu
            close_item = Gtk.MenuItem.new_with_mnemonic("_Close Private Message")
            close_item.connect("activate", lambda w: self.on_close_pm(None))
            menu.append(close_item)

        elif identifier.startswith("channel:"):
            # Channel context menu
            part_item = Gtk.MenuItem.new_with_mnemonic("_Leave Channel")
            part_item.connect("activate", lambda w: self.on_part_channel(None))
            menu.append(part_item)

        elif identifier.startswith("mentions:"):
            # Mentions buffer context menu
            close_item = Gtk.MenuItem.new_with_mnemonic("_Close Mentions")
            close_item.connect("activate", lambda w: self.on_close_mentions(None))
            menu.append(close_item)

        # Only show menu if we added items
        if menu.get_children():
            menu.show_all()

            # Handle both event objects and plain timestamps
            if isinstance(event_or_time, int):
                menu.popup(None, None, None, None, 0, event_or_time)
            else:
                menu.popup(None, None, None, None, event_or_time.button, event_or_time.time)

    def on_message_entry_key_press(self, widget, event) -> bool:
        """Handle key press in message entry for tab completion and Enter to send"""
        # Handle Enter key to send message (but allow Shift+Enter for new line)
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if not (event.state & Gdk.ModifierType.SHIFT_MASK):
                # Enter without Shift - send message
                self.on_send_message(None)
                return True  # Consume the event
            # Shift+Enter - allow default behavior (insert newline)
            return False

        # Handle Tab key for nickname completion
        if event.keyval == Gdk.KEY_Tab or event.keyval == Gdk.KEY_ISO_Left_Tab:
            # Only do completion in channels (not PMs or server views)
            if not self.current_target or not self.current_target.startswith("#"):
                return False

            # Get current text and cursor position from TextBuffer
            buffer = self.message_entry.get_buffer()
            text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            cursor_mark = buffer.get_insert()
            cursor_iter = buffer.get_iter_at_mark(cursor_mark)
            cursor_pos = cursor_iter.get_offset()

            # If this is the first Tab press, find matches
            if not self.tab_completion_matches:
                # Find the word being completed
                # Search backwards from cursor to find word start
                word_start = cursor_pos
                while word_start > 0 and text[word_start - 1] not in (' ', '\t', '\n'):
                    word_start -= 1

                # Get the partial word
                partial = text[word_start:cursor_pos].lower()

                if not partial:
                    return False

                # Get users in current channel
                users = self.irc_manager.get_channel_users(self.current_server, self.current_target) if self.irc_manager else []

                # Remove mode prefixes (@, +, %, ~, &) and find matches
                matches = []
                for user in users:
                    # Strip mode prefix
                    clean_user = user.lstrip('@+%~&')
                    if clean_user.lower().startswith(partial):
                        matches.append(clean_user)

                if not matches:
                    return False

                # Sort matches alphabetically
                matches.sort(key=str.lower)

                # Store completion state
                self.tab_completion_matches = matches
                self.tab_completion_index = 0
                self.tab_completion_word_start = word_start
                # Store the original text that comes after the partial match
                self.tab_completion_original_after = text[cursor_pos:]
            else:
                # Cycle to next match
                self.tab_completion_index = (self.tab_completion_index + 1) % len(self.tab_completion_matches)

            # Get the completion
            completion = self.tab_completion_matches[self.tab_completion_index]

            # Check if we're at the start of the message
            is_start = self.tab_completion_word_start == 0

            # Build the completed text using stored original positions
            before = text[:self.tab_completion_word_start]
            # Always use the original "after" text we stored on first Tab
            after = self.tab_completion_original_after

            if is_start:
                # Add colon and space at start of message
                new_text = before + completion + ": " + after
                new_cursor_pos = len(before) + len(completion) + 2
            else:
                # Just add space after username
                new_text = before + completion + " " + after
                new_cursor_pos = len(before) + len(completion) + 1

            # Update TextView buffer
            buffer.set_text(new_text)
            # Set cursor position
            cursor_iter = buffer.get_iter_at_offset(new_cursor_pos)
            buffer.place_cursor(cursor_iter)

            # Announce match position with a small delay so screen reader reads username first
            match_position = self.tab_completion_index + 1
            total_matches = len(self.tab_completion_matches)

            def announce_match_position():
                if total_matches == 1:
                    self.announce_to_screen_reader("1 match")
                else:
                    self.announce_to_screen_reader(f"match {match_position} of {total_matches}")
                return False  # Don't repeat

            # Delay announcement by 40ms to let Orca announce the text change first
            GLib.timeout_add(40, announce_match_position)

            return True  # Consume the event
        else:
            # Reset tab completion on any other key
            self.tab_completion_matches = []
            self.tab_completion_index = 0
            self.tab_completion_original_after = ""
            return False

    def on_send_message(self, widget) -> None:
        """Handle send message"""
        # Get text from TextView buffer
        buffer = self.message_entry.get_buffer()
        message = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()

        if not message:
            return

        if not self.current_server or not self.current_target:
            self.show_error_dialog("No channel selected", "Please select a server or channel first.")
            return

        # Send via IRC manager
        if self.irc_manager:
            # Check if it's a command
            if message.startswith("/"):
                self._handle_command(message)
            else:
                # Send message (may be split into chunks if too long)
                sent_chunks = self.irc_manager.send_message(self.current_server, self.current_target, message)

                # Add each sent chunk to display
                nickname = self.config_manager.get_nickname() if self.config_manager else "You"
                for chunk in sent_chunks:
                    self.add_message(self.current_server, self.current_target, nickname, chunk)

        # Clear TextView buffer
        buffer.set_text("")

        # Reset tab completion state when sending
        self.tab_completion_matches = []
        self.tab_completion_index = 0
        self.tab_completion_original_after = ""

    def _handle_command(self, command: str) -> None:
        """Handle IRC commands"""
        parts = command.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/join" and args:
            if self.irc_manager:
                self.irc_manager.join_channel(self.current_server, args)

        elif cmd == "/part" or cmd == "/leave":
            if self.current_target and self.current_target.startswith("#"):
                if self.irc_manager:
                    self.irc_manager.part_channel(self.current_server, self.current_target, args)

        elif cmd == "/me" and args:
            # Send CTCP ACTION message (may be split into chunks if too long)
            if self.current_target and self.irc_manager:
                sent_chunks = self.irc_manager.send_action(self.current_server, self.current_target, args)
                # Show each action chunk in our own view
                connection = self.irc_manager.connections.get(self.current_server)
                our_nick = connection.nickname if connection else "You"
                for chunk in sent_chunks:
                    self.add_action_message(self.current_server, self.current_target, our_nick, chunk)

        elif cmd == "/msg":
            # /msg <nick> <message> - Send private message
            msg_parts = args.split(None, 1)
            if len(msg_parts) >= 2:
                nick = msg_parts[0].lstrip('@+%~&')
                message = msg_parts[1]
                if self.irc_manager:
                    # Send the message (may be split into chunks if too long)
                    sent_chunks = self.irc_manager.send_message(self.current_server, nick, message)
                    # Open PM window and show our message
                    pm_iter = self.add_pm_to_tree(self.current_server, nick)
                    if pm_iter:
                        path = self.tree_store.get_path(pm_iter)
                        self.tree_view.set_cursor(path, None, False)
                    # Add each sent chunk to the PM buffer
                    connection = self.irc_manager.connections.get(self.current_server)
                    our_nick = connection.nickname if connection else "You"
                    for chunk in sent_chunks:
                        self.add_message(self.current_server, nick, our_nick, chunk)
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /msg <nick> <message>")

        elif cmd == "/query":
            # /query <nick> [message] - Open PM window, optionally send message
            query_parts = args.split(None, 1)
            if len(query_parts) >= 1:
                nick = query_parts[0].lstrip('@+%~&')
                message = query_parts[1] if len(query_parts) > 1 else None
                # Open PM window
                pm_iter = self.add_pm_to_tree(self.current_server, nick)
                if pm_iter:
                    path = self.tree_store.get_path(pm_iter)
                    self.tree_view.set_cursor(path, None, False)
                # Add system message if no message provided
                key = (self.current_server, nick)
                if key not in self.message_buffers or self.message_buffers[key].get_char_count() == 0:
                    self.add_system_message(self.current_server, nick,
                                           f"Private conversation with {nick}")
                # Send message if provided (may be split into chunks if too long)
                if message and self.irc_manager:
                    sent_chunks = self.irc_manager.send_message(self.current_server, nick, message)
                    connection = self.irc_manager.connections.get(self.current_server)
                    our_nick = connection.nickname if connection else "You"
                    for chunk in sent_chunks:
                        self.add_message(self.current_server, nick, our_nick, chunk)
                # Focus message entry
                self.message_entry.grab_focus()
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /query <nick> [message]")

        elif cmd == "/nick" and args:
            # /nick <newnick> - Change nickname
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection and connection.irc:
                    connection.irc.quote(f"NICK {args}")
                    self.add_system_message(self.current_server, self.current_target,
                                           f"Changing nickname to {args}...")

        elif cmd == "/topic":
            # /topic [new topic] - View or set channel topic
            if self.current_target and self.current_target.startswith("#"):
                if self.irc_manager:
                    connection = self.irc_manager.connections.get(self.current_server)
                    if connection and connection.irc:
                        if args:
                            # Set topic
                            connection.irc.quote(f"TOPIC {self.current_target} :{args}")
                            self.add_system_message(self.current_server, self.current_target,
                                                   f"Setting topic to: {args}")
                        else:
                            # Request topic
                            connection.irc.quote(f"TOPIC {self.current_target}")
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "/topic can only be used in channels")

        elif cmd == "/whois" and args:
            # /whois <nick> - Get information about a user
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection and connection.irc:
                    nick = args.lstrip('@+%~&')
                    connection.irc.quote(f"WHOIS {nick}")
                    self.add_system_message(self.current_server, self.current_target,
                                           f"Sent WHOIS query for {nick}")

        elif cmd == "/kick":
            # /kick <nick> [reason] - Kick a user from channel
            if self.current_target and self.current_target.startswith("#"):
                kick_parts = args.split(None, 1)
                if len(kick_parts) >= 1:
                    nick = kick_parts[0].lstrip('@+%~&')
                    reason = kick_parts[1] if len(kick_parts) > 1 else ""
                    if self.irc_manager:
                        connection = self.irc_manager.connections.get(self.current_server)
                        if connection and connection.irc:
                            if reason:
                                connection.irc.quote(f"KICK {self.current_target} {nick} :{reason}")
                            else:
                                connection.irc.quote(f"KICK {self.current_target} {nick}")
                else:
                    self.add_system_message(self.current_server, self.current_target,
                                           "Usage: /kick <nick> [reason]")
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "/kick can only be used in channels")

        elif cmd == "/mode" and args:
            # /mode <target> <modes> - Set channel or user modes
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection and connection.irc:
                    connection.irc.quote(f"MODE {args}")
                    self.add_system_message(self.current_server, self.current_target,
                                           f"Setting mode: {args}")

        elif cmd == "/away":
            # /away [message] - Set away status (empty message to unset)
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection and connection.irc:
                    if args:
                        connection.irc.quote(f"AWAY :{args}")
                        self.add_system_message(self.current_server, self.current_target,
                                               f"Setting away: {args}")
                    else:
                        connection.irc.quote("AWAY")
                        self.add_system_message(self.current_server, self.current_target,
                                               "Removing away status")

        elif cmd == "/invite":
            # /invite <nick> [channel] - Invite user to channel
            invite_parts = args.split(None, 1)
            if len(invite_parts) >= 1:
                nick = invite_parts[0].lstrip('@+%~&')
                channel = invite_parts[1] if len(invite_parts) > 1 else self.current_target
                if channel and channel.startswith("#"):
                    if self.irc_manager:
                        connection = self.irc_manager.connections.get(self.current_server)
                        if connection and connection.irc:
                            connection.irc.quote(f"INVITE {nick} {channel}")
                            self.add_system_message(self.current_server, self.current_target,
                                                   f"Invited {nick} to {channel}")
                else:
                    self.add_system_message(self.current_server, self.current_target,
                                           "Usage: /invite <nick> [channel]")
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /invite <nick> [channel]")

        elif cmd == "/raw" and args:
            # /raw <command> - Send raw IRC command
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection and connection.irc:
                    connection.irc.quote(args)
                    self.add_system_message(self.current_server, self.current_target,
                                           f"Sent raw command: {args}")

        elif cmd == "/list":
            # /list - Request and display channel list
            if self.irc_manager:
                connection = self.irc_manager.connections.get(self.current_server)
                if connection:
                    if connection.request_channel_list():
                        self.add_system_message(self.current_server, self.current_target,
                                               "Requesting channel list from server...")
                    else:
                        self.add_system_message(self.current_server, self.current_target,
                                               "Channel list request already in progress")

        elif cmd == "/quit":
            self.on_quit(None)

        elif cmd == "/exec":
            # /exec [-o] <command> - Execute shell command
            # -o: send output to current channel/PM instead of displaying locally
            if not args:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /exec [-o] <command>")
                return

            send_output = False
            exec_command = args

            # Check for -o flag
            if args.startswith("-o "):
                send_output = True
                exec_command = args[3:].strip()
            elif args == "-o":
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /exec [-o] <command>")
                return

            if not exec_command:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /exec [-o] <command>")
                return

            # Execute command and capture output
            try:
                result = subprocess.run(
                    exec_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                output = result.stdout
                if result.stderr:
                    output = output + result.stderr if output else result.stderr
            except subprocess.TimeoutExpired:
                self.add_system_message(self.current_server, self.current_target,
                                       f"Command timed out: {exec_command}")
                return
            except Exception as e:
                self.add_system_message(self.current_server, self.current_target,
                                       f"Error executing command: {e}")
                return

            # Process output
            if not output or not output.strip():
                self.add_system_message(self.current_server, self.current_target,
                                       f"Command produced no output: {exec_command}")
                return

            # Split output into lines
            lines = output.rstrip('\n').split('\n')

            if send_output:
                # Send output to current channel/PM as messages
                if self.current_target and self.irc_manager:
                    for line in lines:
                        if line:  # Skip empty lines
                            sent_chunks = self.irc_manager.send_message(
                                self.current_server, self.current_target, line
                            )
                            # Show in our own view
                            connection = self.irc_manager.connections.get(self.current_server)
                            our_nick = connection.nickname if connection else "You"
                            for chunk in sent_chunks:
                                self.add_message(self.current_server, self.current_target,
                                               our_nick, chunk)
                else:
                    self.add_system_message(self.current_server, self.current_target,
                                           "No active channel or PM to send output to")
            else:
                # Display output locally only
                # Determine if we should announce based on settings
                should_announce = (
                    self.config_manager and
                    self.config_manager.should_announce_all_messages()
                )
                for line in lines:
                    if line:  # Skip empty lines
                        self.add_system_message(
                            self.current_server, self.current_target,
                            line, announce=should_announce
                        )

        else:
            self.add_system_message(self.current_server, self.current_target,
                                   f"Unknown command: {cmd}")

    def on_connect_server(self, widget) -> None:
        """Show connect to server dialog"""
        # Check if there are any servers configured
        servers = self.config_manager.get_servers()
        if not servers:
            self.show_info_dialog("No Servers", "No servers configured. Use Server > Manage Servers to add servers.")
            return

        # Check if there are any disconnected servers
        has_disconnected = False
        for server in servers:
            if not self.irc_manager.is_connected(server.get("name")):
                has_disconnected = True
                break

        if not has_disconnected:
            self.show_info_dialog("Already Connected", "You are already connected to all configured servers.")
            return

        # Show connect dialog
        dialog = ConnectServerDialog(self, self.config_manager, self.irc_manager)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            server = dialog.get_selected_server()
            if server:
                server_name = server.get("name")
                if self.irc_manager.connect_server(server):
                    self.add_server_to_tree(server_name)
                    self.update_status(f"Connecting to {server_name}...")
                else:
                    self.show_error_dialog("Connection Failed", f"Failed to connect to {server_name}")

        dialog.destroy()

    def on_disconnect_server(self, widget) -> None:
        """Disconnect from current server"""
        if self.current_server and self.irc_manager:
            quit_message = self.config_manager.get_quit_message() if self.config_manager else "Leaving"
            self.irc_manager.disconnect_server(self.current_server, quit_message)

    def on_manage_servers(self, widget) -> None:
        """Show server management dialog"""
        # Will be implemented in server dialog
        from .server_dialog import ServerManagementDialog
        dialog = ServerManagementDialog(self, self.config_manager, self.irc_manager)
        dialog.run()
        dialog.destroy()

    def on_join_channel(self, widget) -> None:
        """Show join channel dialog"""
        if not self.current_server:
            self.show_error_dialog("No server", "Please select a server first.")
            return

        dialog = Gtk.Dialog(title="Join Channel", parent=self, modal=True)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_border_width(12)

        label = Gtk.Label.new_with_mnemonic("_Channel name:")
        entry = Gtk.Entry()
        entry.set_placeholder_text("#channel")
        entry.set_activates_default(True)
        label.set_mnemonic_widget(entry)

        box.pack_start(label, False, False, 0)
        box.pack_start(entry, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            channel = entry.get_text().strip()
            if channel and self.irc_manager:
                self.irc_manager.join_channel(self.current_server, channel)

        dialog.destroy()

    def on_part_channel(self, widget) -> None:
        """Leave current channel"""
        if self.current_target and self.current_target.startswith("#"):
            if self.irc_manager:
                self.irc_manager.part_channel(self.current_server, self.current_target)

    def on_close_pm(self, widget) -> None:
        """Close current private message"""
        if self.current_target and not self.current_target.startswith("#") and self.current_target != self.current_server:
            server_name = self.current_server
            closed_identifier = f"pm:{server_name}:{self.current_target}"

            # Get identifier of previous buffer BEFORE removal
            prev_identifier = self._get_previous_buffer_identifier(server_name, closed_identifier)

            # Remove PM from tree
            self.remove_pm_from_tree(server_name, self.current_target)

            # Navigate to previous buffer by identifier
            self._navigate_to_identifier(prev_identifier)

    def on_close_mentions(self, widget) -> None:
        """Close current server's mentions buffer"""
        if self.current_target == "mentions" and self.current_server:
            server_name = self.current_server
            closed_identifier = f"mentions:{server_name}"

            # Get identifier of previous buffer BEFORE removal
            prev_identifier = self._get_previous_buffer_identifier(server_name, closed_identifier)

            # Remove mentions buffer from tree
            if server_name in self.mentions_iters:
                mentions_iter = self.mentions_iters[server_name]
                self.tree_store.remove(mentions_iter)
                del self.mentions_iters[server_name]

                # Remove buffer from message_buffers
                key = (server_name, "mentions")
                if key in self.message_buffers:
                    del self.message_buffers[key]

            # Navigate to previous buffer by identifier
            self._navigate_to_identifier(prev_identifier)

    def on_preferences(self, widget) -> None:
        """Show preferences dialog"""
        from .preferences_dialog import PreferencesDialog
        dialog = PreferencesDialog(self, self.config_manager, self.sound_manager, self.log_manager)
        dialog.run()
        dialog.destroy()

    def on_about(self, widget) -> None:
        """Show about dialog"""
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("Access IRC")
        dialog.set_version("1.5.0")
        dialog.set_comments("An accessible IRC client for Linux with screen reader support")
        dialog.set_website("https://github.com/destructatron/access-irc")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_authors(["Access IRC Contributors"])
        dialog.run()
        dialog.destroy()

    def on_users_list_button_press(self, widget, event) -> bool:
        """Handle button press on users list (for context menu)"""
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:  # Right-click
            # Get the clicked row
            row = self.users_list.get_row_at_y(int(event.y))
            if row:
                self.users_list.select_row(row)
                label = row.get_child()
                if label:
                    username = label.get_text()
                    self._show_user_context_menu(username, event)
                    return True
        return False

    def on_users_list_key_press(self, widget, event) -> bool:
        """Handle key press on users list (for keyboard shortcuts)"""
        # Handle Tab/Shift+Tab - move focus out of the list
        if event.keyval == Gdk.KEY_Tab or event.keyval == Gdk.KEY_ISO_Left_Tab:
            # Stop the signal from propagating to prevent ListBox internal navigation
            widget.stop_emission_by_name("key-press-event")

            if event.state & Gdk.ModifierType.SHIFT_MASK:
                # Shift+Tab - move to previous widget (message view)
                self.message_view.grab_focus()
            else:
                # Tab - move to next widget (message entry)
                self.message_entry.grab_focus()
            return True  # Consume the event

        # Get the selected row for other operations
        row = self.users_list.get_selected_row()
        if not row:
            return False

        label = row.get_child()
        if not label:
            return False

        username = label.get_text()

        # Handle Menu key or Shift+F10 - show context menu
        if event.keyval == Gdk.KEY_Menu or \
           (event.keyval == Gdk.KEY_F10 and event.state & Gdk.ModifierType.SHIFT_MASK):
            # Show context menu with keyboard event time
            self._show_user_context_menu(username, event.time)
            return True

        return False

    def on_users_list_row_activated(self, listbox, row) -> None:
        """Handle double-click or Enter on a user row"""
        label = row.get_child()
        if label:
            username = label.get_text()
            self.on_user_private_message(None, username)

    def _show_user_context_menu(self, username: str, event_or_time) -> None:
        """
        Show context menu for a user

        Args:
            username: The username that was right-clicked
            event_or_time: Either a button press event or a timestamp
        """
        menu = Gtk.Menu()

        # Private message option
        pm_item = Gtk.MenuItem.new_with_mnemonic("_Private Message")
        pm_item.connect("activate", self.on_user_private_message, username)
        menu.append(pm_item)

        # WHOIS option
        whois_item = Gtk.MenuItem.new_with_mnemonic("_WHOIS")
        whois_item.connect("activate", self.on_user_whois, username)
        menu.append(whois_item)

        menu.show_all()

        # Handle both event objects and plain timestamps
        if isinstance(event_or_time, int):
            # It's a timestamp (from keyboard event)
            menu.popup(None, None, None, None, 0, event_or_time)
        else:
            # It's an event object (from mouse click)
            menu.popup(None, None, None, None, event_or_time.button, event_or_time.time)

    def on_user_private_message(self, widget, username: str) -> None:
        """
        Open private message with user

        Args:
            username: Username to send PM to
        """
        if not self.current_server:
            return

        # Strip mode prefixes from username
        username = username.lstrip('@+%~&')

        # Add PM to tree (or get existing)
        pm_iter = self.add_pm_to_tree(self.current_server, username)

        # Select the PM in the tree (use set_cursor to sync both selection and cursor)
        if pm_iter:
            path = self.tree_store.get_path(pm_iter)
            self.tree_view.set_cursor(path, None, False)

            # The selection changed handler will take care of:
            # - Setting current_server and current_target
            # - Loading the message buffer
            # - Updating the channel label
            # - Clearing the users list
        else:
            # Fallback if tree update failed
            self.current_target = username
            self.channel_label.set_text(f"{self.current_server} / PM: {username}")

            # Create buffer if needed
            key = (self.current_server, username)
            if key not in self.message_buffers:
                self.message_buffers[key] = Gtk.TextBuffer()
            self.message_view.set_buffer(self.message_buffers[key])

            # Clear users list (PMs don't have user lists)
            for child in self.users_list.get_children():
                self.users_list.remove(child)

        # Focus the message entry
        self.message_entry.grab_focus()

        # Add system message if it's a new PM
        key = (self.current_server, username)
        if key not in self.message_buffers or self.message_buffers[key].get_char_count() == 0:
            self.add_system_message(self.current_server, username,
                                   f"Private conversation with {username}")

    def on_user_whois(self, widget, username: str) -> None:
        """
        Send WHOIS query for user

        Args:
            username: Username to query
        """
        if self.current_server and self.irc_manager:
            # Send raw WHOIS command
            connection = self.irc_manager.connections.get(self.current_server)
            if connection and connection.irc:
                # Strip mode prefixes before sending WHOIS
                nick = username.lstrip('@+%~&')
                connection.irc.quote(f"WHOIS {nick}")
                self.add_system_message(self.current_server, self.current_target,
                                       f"Sent WHOIS query for {nick}")

    def on_quit(self, widget) -> None:
        """Quit application"""
        # Disconnect all servers with configured quit message
        if self.irc_manager:
            quit_message = self.config_manager.get_quit_message() if self.config_manager else "Leaving"
            self.irc_manager.disconnect_all(quit_message)

        # Cleanup sound
        if self.sound_manager:
            self.sound_manager.cleanup()

        Gtk.main_quit()

    def show_channel_list_dialog(self, server: str, channels: list) -> None:
        """
        Show channel list dialog

        Args:
            server: Server name
            channels: List of channel dicts with 'channel', 'users', 'topic' keys
        """
        dialog = ChannelListDialog(self, server, channels, self.irc_manager)
        dialog.run()
        dialog.destroy()

    # Helper dialogs
    def show_error_dialog(self, title: str, message: str) -> None:
        """Show error dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def show_info_dialog(self, title: str, message: str) -> None:
        """Show info dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()


class ChannelListDialog(Gtk.Dialog):
    """Dialog to display and filter channel list from IRC server"""

    # Maximum number of channels to display per page
    PAGE_SIZE = 100

    def __init__(self, parent, server: str, channels: list, irc_manager):
        """
        Initialize channel list dialog

        Args:
            parent: Parent window
            server: Server name
            channels: List of channel dicts with 'channel', 'users', 'topic' keys
            irc_manager: IRCManager instance for joining channels
        """
        super().__init__(title=f"Channel List - {server}", parent=parent, modal=True)
        self.set_default_size(700, 500)
        self.set_border_width(12)

        self.server = server
        self.all_channels = channels
        self.irc_manager = irc_manager
        self.filtered_channels = []
        self.current_page = 0

        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        content = self.get_content_area()
        content.set_spacing(12)

        # Search box
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_label = Gtk.Label.new_with_mnemonic("_Filter:")
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Type to filter channels...")
        self.search_entry.connect("changed", self.on_search_changed)
        search_label.set_mnemonic_widget(self.search_entry)
        search_box.pack_start(search_label, False, False, 0)
        search_box.pack_start(self.search_entry, True, True, 0)
        content.pack_start(search_box, False, False, 0)

        # Status label
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        content.pack_start(self.status_label, False, False, 0)

        # Create list store: channel name, user count, topic
        self.list_store = Gtk.ListStore(str, int, str)

        # Create tree view
        self.tree_view = Gtk.TreeView(model=self.list_store)
        self.tree_view.set_headers_visible(True)
        self.tree_view.connect("row-activated", self.on_row_activated)
        self.tree_view.connect("key-press-event", self.on_key_press)

        # Channel column
        channel_renderer = Gtk.CellRendererText()
        channel_column = Gtk.TreeViewColumn("Channel", channel_renderer, text=0)
        channel_column.set_sort_column_id(0)
        channel_column.set_resizable(True)
        channel_column.set_min_width(150)
        self.tree_view.append_column(channel_column)

        # Users column
        users_renderer = Gtk.CellRendererText()
        users_column = Gtk.TreeViewColumn("Users", users_renderer, text=1)
        users_column.set_sort_column_id(1)
        users_column.set_resizable(True)
        users_column.set_min_width(60)
        self.tree_view.append_column(users_column)

        # Topic column
        topic_renderer = Gtk.CellRendererText()
        topic_renderer.set_property("ellipsize", 3)  # PANGO_ELLIPSIZE_END
        topic_column = Gtk.TreeViewColumn("Topic", topic_renderer, text=2)
        topic_column.set_sort_column_id(2)
        topic_column.set_resizable(True)
        topic_column.set_expand(True)
        self.tree_view.append_column(topic_column)

        # Scrolled window for tree
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.tree_view)
        content.pack_start(scrolled, True, True, 0)

        # Pagination box
        pagination_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.prev_button = Gtk.Button.new_with_mnemonic("_Previous")
        self.prev_button.connect("clicked", self.on_prev_clicked)
        pagination_box.pack_start(self.prev_button, False, False, 0)

        self.page_label = Gtk.Label()
        pagination_box.pack_start(self.page_label, True, True, 0)

        self.next_button = Gtk.Button.new_with_mnemonic("_Next")
        self.next_button.connect("clicked", self.on_next_clicked)
        pagination_box.pack_start(self.next_button, False, False, 0)

        content.pack_start(pagination_box, False, False, 0)

        # Help text
        help_label = Gtk.Label()
        help_label.set_markup("<i>Press Enter to join the selected channel</i>")
        help_label.set_xalign(0)
        content.pack_start(help_label, False, False, 0)

        # Initial population
        self.apply_filter("")

        self.show_all()

        # Focus search entry
        self.search_entry.grab_focus()

    def apply_filter(self, filter_text: str) -> None:
        """
        Apply filter and reset to first page

        Args:
            filter_text: Text to filter channels by
        """
        filter_lower = filter_text.lower()

        # Filter channels
        if filter_lower:
            self.filtered_channels = [
                ch for ch in self.all_channels
                if filter_lower in ch["channel"].lower() or filter_lower in ch["topic"].lower()
            ]
        else:
            self.filtered_channels = list(self.all_channels)

        # Sort by user count descending (most popular first)
        self.filtered_channels.sort(key=lambda x: x["users"], reverse=True)

        # Reset to first page
        self.current_page = 0
        self.update_page()

    def update_page(self) -> None:
        """Update the displayed page"""
        self.list_store.clear()

        total_filtered = len(self.filtered_channels)
        total_pages = max(1, (total_filtered + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        # Calculate slice for current page
        start_idx = self.current_page * self.PAGE_SIZE
        end_idx = start_idx + self.PAGE_SIZE
        page_channels = self.filtered_channels[start_idx:end_idx]

        for ch in page_channels:
            self.list_store.append([ch["channel"], ch["users"], ch["topic"]])

        # Update pagination buttons
        self.prev_button.set_sensitive(self.current_page > 0)
        self.next_button.set_sensitive(end_idx < total_filtered)

        # Update page label
        if total_filtered > 0:
            self.page_label.set_text(f"Page {self.current_page + 1} of {total_pages}")
        else:
            self.page_label.set_text("No channels")

        # Update status label
        total = len(self.all_channels)
        displayed = len(page_channels)
        filter_text = self.search_entry.get_text()

        if filter_text:
            self.status_label.set_text(
                f"Showing {start_idx + 1}-{start_idx + displayed} of {total_filtered} matching channels ({total} total)"
            )
        else:
            self.status_label.set_text(
                f"Showing {start_idx + 1}-{start_idx + displayed} of {total} channels (sorted by user count)"
            )

    def on_search_changed(self, entry) -> None:
        """Handle search entry text change"""
        self.apply_filter(entry.get_text())

    def on_prev_clicked(self, button) -> None:
        """Handle Previous button click"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page()
            self.announce_range()

    def on_next_clicked(self, button) -> None:
        """Handle Next button click"""
        total_filtered = len(self.filtered_channels)
        if (self.current_page + 1) * self.PAGE_SIZE < total_filtered:
            self.current_page += 1
            self.update_page()
            self.announce_range()

    def announce_range(self) -> None:
        """Announce current channel range to screen reader"""
        total_filtered = len(self.filtered_channels)
        start_idx = self.current_page * self.PAGE_SIZE
        end_idx = min(start_idx + self.PAGE_SIZE, total_filtered)

        message = f"Showing channels {start_idx + 1} to {end_idx} of {total_filtered}"

        # Get parent window and announce
        parent = self.get_transient_for()
        if parent and hasattr(parent, 'announce_to_screen_reader'):
            parent.announce_to_screen_reader(message)

    def on_row_activated(self, tree_view, path, column) -> None:
        """Handle double-click or Enter on a row"""
        self.join_selected_channel()

    def on_key_press(self, widget, event) -> bool:
        """Handle key press in tree view"""
        if event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter:
            self.join_selected_channel()
            return True
        return False

    def join_selected_channel(self) -> None:
        """Join the currently selected channel"""
        selection = self.tree_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            channel = model.get_value(tree_iter, 0)
            if self.irc_manager:
                self.irc_manager.join_channel(self.server, channel)
            self.response(Gtk.ResponseType.CLOSE)


class ConnectServerDialog(Gtk.Dialog):
    """Simple dialog to select and connect to a configured server"""

    def __init__(self, parent, config_manager, irc_manager):
        """
        Initialize connect server dialog

        Args:
            parent: Parent window
            config_manager: ConfigManager instance
            irc_manager: IRCManager instance
        """
        super().__init__(title="Connect to Server", parent=parent, modal=True)
        self.set_default_size(400, 300)
        self.set_border_width(12)

        self.config = config_manager
        self.irc_manager = irc_manager
        self.parent_window = parent

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_CONNECT, Gtk.ResponseType.OK
        )

        self._build_ui()
        self._load_servers()

    def _build_ui(self) -> None:
        """Build dialog UI"""

        box = self.get_content_area()
        box.set_spacing(6)

        # Label
        label = Gtk.Label(label="Select a server to connect to:")
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        # Scrolled window for server list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        box.pack_start(scrolled, True, True, 0)

        # ListStore: server_name, host, server_data
        self.store = Gtk.ListStore(str, str, object)
        self.tree_view = Gtk.TreeView(model=self.store)
        self.tree_view.set_headers_visible(True)

        # Name column
        name_renderer = Gtk.CellRendererText()
        name_column = Gtk.TreeViewColumn("Server", name_renderer, text=0)
        name_column.set_expand(True)
        self.tree_view.append_column(name_column)

        # Host column
        host_renderer = Gtk.CellRendererText()
        host_column = Gtk.TreeViewColumn("Host", host_renderer, text=1)
        host_column.set_expand(True)
        self.tree_view.append_column(host_column)

        # Double-click to connect
        self.tree_view.connect("row-activated", self.on_row_activated)

        scrolled.add(self.tree_view)

        self.show_all()

    def _load_servers(self) -> None:
        """Load servers from config"""
        self.store.clear()

        servers = self.config.get_servers()
        if not servers:
            # No servers configured
            return

        for server in servers:
            name = server.get("name", "Unknown")
            host = server.get("host", "")

            # Skip servers that are already connected
            if not self.irc_manager.is_connected(name):
                self.store.append([name, host, server])

        # Select first server by default
        if len(self.store) > 0:
            self.tree_view.set_cursor(Gtk.TreePath(0))

    def on_row_activated(self, tree_view, path, column) -> None:
        """Handle double-click on server"""
        self.response(Gtk.ResponseType.OK)

    def get_selected_server(self):
        """Get selected server data"""
        selection = self.tree_view.get_selection()
        model, iter = selection.get_selected()

        if not iter:
            return None

        return model.get_value(iter, 2)  # Return server data
