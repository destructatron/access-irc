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


class AccessibleIRCWindow(Gtk.Window):
    """Main window for accessible IRC client"""

    def __init__(self, app_title: str = "Access IRC"):
        """
        Initialize main window

        Args:
            app_title: Application window title
        """
        super().__init__(title=app_title)
        self.set_default_size(1000, 700)
        self.set_border_width(6)

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

        # Reference to paned widget for resizing
        self.h_paned = None

        # Reference to users list widget
        self.users_list = None

        # Tab completion state
        self.tab_completion_matches = []
        self.tab_completion_index = 0
        self.tab_completion_word_start = 0
        self.tab_completion_original_after = ""

        # Build UI
        self._build_ui()

        # Connect to realize signal to set paned position after window is sized
        self.connect("realize", self._on_window_realized)

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
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(250)
        main_box.pack_start(paned, True, True, 0)

        # Left side: Server and channel list
        left_panel = self._create_left_panel()
        paned.add1(left_panel)

        # Right side: Chat area
        right_panel = self._create_right_panel()
        paned.add2(right_panel)

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
        self.h_paned.add1(chat_scrolled)

        # TextView for messages (read-only but navigable)
        self.message_view = Gtk.TextView()
        self.message_view.set_editable(False)
        self.message_view.set_cursor_visible(True)
        self.message_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.message_view.set_left_margin(6)
        self.message_view.set_right_margin(6)

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
        users_scrolled.set_min_content_width(150)
        users_scrolled.show()
        users_box.pack_start(users_scrolled, True, True, 0)

        # ListBox for users (simpler than TreeView for a flat list)
        self.users_list = Gtk.ListBox()
        self.users_list.set_selection_mode(Gtk.SelectionMode.SINGLE)

        # Don't participate in tab chain (only accessible via Alt+U mnemonic)
        # This prevents Tab from cycling through individual users
        self.users_list.set_focus_on_click(False)
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

        # Entry for message input
        self.message_entry = Gtk.Entry()
        self.message_entry.set_placeholder_text("Type your message here...")
        self.message_entry.connect("activate", self.on_send_message)
        self.message_entry.connect("key-press-event", self.on_message_entry_key_press)
        input_label.set_mnemonic_widget(self.message_entry)
        input_box.pack_start(self.message_entry, True, True, 0)

        # Send button
        send_button = Gtk.Button(label="Send")
        send_button.connect("clicked", self.on_send_message)
        input_box.pack_start(send_button, False, False, 0)

        box.pack_start(input_box, False, False, 0)

        return box

    def _on_window_realized(self, widget) -> None:
        """Set paned position after window is realized and sized"""
        if self.h_paned:
            # Set position to 70% of window width, leaving 30% for users list
            allocation = self.h_paned.get_allocation()
            position = int(allocation.width * 0.70)
            self.h_paned.set_position(position)

    def set_managers(self, irc_manager, sound_manager, config_manager) -> None:
        """
        Set manager references

        Args:
            irc_manager: IRCManager instance
            sound_manager: SoundManager instance
            config_manager: ConfigManager instance
        """
        self.irc_manager = irc_manager
        self.sound_manager = sound_manager
        self.config_manager = config_manager

    def announce_to_screen_reader(self, message: str) -> None:
        """
        Send announcement to screen reader via AT-SPI2

        Args:
            message: Message to announce
        """
        try:
            # Get accessible object from main window
            atk_object = self.get_accessible()

            # Emit notification signal for screen readers
            # This signal will be picked up by Orca and read aloud
            atk_object.emit("notification", message)
        except Exception as e:
            # Fallback to older announcement signal
            try:
                atk_object = self.get_accessible()
                atk_object.emit("announcement", message)
            except Exception as e2:
                print(f"Failed to emit accessibility announcement: {e2}")

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

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Handle announcements and sounds
        if is_mention:
            # Announce mention to screen reader (if mentions OR all messages is enabled)
            if self.config_manager.should_announce_mentions() or self.config_manager.should_announce_all_messages():
                self.announce_to_screen_reader(f"{sender} mentioned you in {target}: {message}")

            # Play mention sound
            if self.sound_manager:
                self.sound_manager.play_mention()

        elif not is_system:
            # Regular message
            if self.config_manager.should_announce_all_messages():
                self.announce_to_screen_reader(f"{sender} in {target}: {message}")

            # Play message sound
            if self.sound_manager:
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

    def add_action_message(self, server: str, target: str, sender: str, action: str) -> None:
        """
        Add CTCP ACTION message (/me)

        Args:
            server: Server name
            target: Channel or PM recipient
            sender: User performing the action
            action: Action text
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

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Announce to screen reader if configured
        if self.config_manager.should_announce_all_messages():
            self.announce_to_screen_reader(f"{sender} {action}")

        # Play message sound
        if self.sound_manager:
            self.sound_manager.play_message()

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

        # If this is the current view, update display and scroll
        if self.current_server == server and self.current_target == target:
            self.message_view.set_buffer(buffer)
            self._scroll_to_bottom()

        # Announce to screen reader if configured
        if self.config_manager.should_announce_all_messages():
            self.announce_to_screen_reader(f"Notice from {sender}: {message}")

        # Play notice sound
        if self.sound_manager:
            self.sound_manager.play_notice()

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

        print(f"DEBUG: update_users_list called for {server}/{channel}")

        # Clear current users list
        for child in self.users_list.get_children():
            self.users_list.remove(child)

        # Only show users for channels (not PMs or server views)
        if server and channel and channel.startswith("#") and self.irc_manager:
            users = self.irc_manager.get_channel_users(server, channel)
            print(f"DEBUG: Got {len(users)} users: {users}")
            for user in users:
                label = Gtk.Label(label=user, xalign=0)
                label.set_margin_start(6)
                label.set_margin_end(6)
                label.set_margin_top(3)
                label.set_margin_bottom(3)
                self.users_list.add(label)

            # Show all the new labels
            self.users_list.show_all()
        else:
            print(f"DEBUG: Not showing users - server={server}, channel={channel}, startswith#={channel.startswith('#') if channel else False}, has_manager={self.irc_manager is not None}")

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
            TreeIter for the channel
        """
        server_name = self.tree_store.get_value(server_iter, 0)
        return self.tree_store.append(server_iter, [channel, f"channel:{server_name}:{channel}"])

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

    def on_window_key_press(self, widget, event) -> bool:
        """Handle window-level keyboard shortcuts"""
        # Ctrl+W - Close current PM or leave channel
        if event.keyval == Gdk.KEY_w and event.state & Gdk.ModifierType.CONTROL_MASK:
            if self.current_target and not self.current_target.startswith("#") and self.current_target != self.current_server:
                # It's a PM - close it
                self.on_close_pm(None)
                return True
            elif self.current_target and self.current_target.startswith("#"):
                # It's a channel - leave it
                self.on_part_channel(None)
                return True
        return False

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

        # Only show menu if we added items
        if menu.get_children():
            menu.show_all()

            # Handle both event objects and plain timestamps
            if isinstance(event_or_time, int):
                menu.popup(None, None, None, None, 0, event_or_time)
            else:
                menu.popup(None, None, None, None, event_or_time.button, event_or_time.time)

    def on_message_entry_key_press(self, widget, event) -> bool:
        """Handle key press in message entry for tab completion"""
        # Handle Tab key for nickname completion
        if event.keyval == Gdk.KEY_Tab or event.keyval == Gdk.KEY_ISO_Left_Tab:
            # Only do completion in channels (not PMs or server views)
            if not self.current_target or not self.current_target.startswith("#"):
                return False

            # Get current text and cursor position
            text = self.message_entry.get_text()
            cursor_pos = self.message_entry.get_position()

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

            # Update entry
            self.message_entry.set_text(new_text)
            self.message_entry.set_position(new_cursor_pos)

            return True  # Consume the event
        else:
            # Reset tab completion on any other key
            self.tab_completion_matches = []
            self.tab_completion_index = 0
            self.tab_completion_original_after = ""
            return False

    def on_send_message(self, widget) -> None:
        """Handle send message"""
        message = self.message_entry.get_text().strip()

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
                print(f"DEBUG: Sending message to {self.current_server}/{self.current_target}: {message}")
                self.irc_manager.send_message(self.current_server, self.current_target, message)

                # Add own message to display
                nickname = self.config_manager.get_nickname() if self.config_manager else "You"
                self.add_message(self.current_server, self.current_target, nickname, message)

        # Clear entry
        self.message_entry.set_text("")

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
            # Send CTCP ACTION message
            if self.current_target and self.irc_manager:
                self.irc_manager.send_action(self.current_server, self.current_target, args)
                # Show the action in our own view
                connection = self.irc_manager.connections.get(self.current_server)
                our_nick = connection.nickname if connection else "You"
                self.add_action_message(self.current_server, self.current_target, our_nick, args)

        elif cmd == "/msg":
            # /msg <nick> <message> - Send private message
            msg_parts = args.split(None, 1)
            if len(msg_parts) >= 2:
                nick = msg_parts[0]
                message = msg_parts[1]
                if self.irc_manager:
                    # Send the message
                    self.irc_manager.send_message(self.current_server, nick, message)
                    # Open PM window and show our message
                    pm_iter = self.add_pm_to_tree(self.current_server, nick)
                    if pm_iter:
                        selection = self.tree_view.get_selection()
                        selection.select_iter(pm_iter)
                    # Add our message to the PM buffer
                    connection = self.irc_manager.connections.get(self.current_server)
                    our_nick = connection.nickname if connection else "You"
                    self.add_message(self.current_server, nick, our_nick, message)
            else:
                self.add_system_message(self.current_server, self.current_target,
                                       "Usage: /msg <nick> <message>")

        elif cmd == "/query":
            # /query <nick> [message] - Open PM window, optionally send message
            query_parts = args.split(None, 1)
            if len(query_parts) >= 1:
                nick = query_parts[0]
                message = query_parts[1] if len(query_parts) > 1 else None
                # Open PM window
                pm_iter = self.add_pm_to_tree(self.current_server, nick)
                if pm_iter:
                    selection = self.tree_view.get_selection()
                    selection.select_iter(pm_iter)
                # Add system message if no message provided
                key = (self.current_server, nick)
                if key not in self.message_buffers or self.message_buffers[key].get_char_count() == 0:
                    self.add_system_message(self.current_server, nick,
                                           f"Private conversation with {nick}")
                # Send message if provided
                if message and self.irc_manager:
                    self.irc_manager.send_message(self.current_server, nick, message)
                    connection = self.irc_manager.connections.get(self.current_server)
                    our_nick = connection.nickname if connection else "You"
                    self.add_message(self.current_server, nick, our_nick, message)
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
                    connection.irc.quote(f"WHOIS {args}")
                    self.add_system_message(self.current_server, self.current_target,
                                           f"Sent WHOIS query for {args}")

        elif cmd == "/kick":
            # /kick <nick> [reason] - Kick a user from channel
            if self.current_target and self.current_target.startswith("#"):
                kick_parts = args.split(None, 1)
                if len(kick_parts) >= 1:
                    nick = kick_parts[0]
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
                nick = invite_parts[0]
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

        elif cmd == "/quit":
            self.on_quit(None)

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

        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_border_width(12)

        label = Gtk.Label.new_with_mnemonic("_Channel name:")
        entry = Gtk.Entry()
        entry.set_placeholder_text("#channel")
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
            # Remove PM from tree
            self.remove_pm_from_tree(self.current_server, self.current_target)

            # Switch to server view
            iter = self.tree_store.get_iter_first()
            while iter:
                if self.tree_store.get_value(iter, 0) == self.current_server:
                    selection = self.tree_view.get_selection()
                    selection.select_iter(iter)
                    break
                iter = self.tree_store.iter_next(iter)

    def on_preferences(self, widget) -> None:
        """Show preferences dialog"""
        from .preferences_dialog import PreferencesDialog
        dialog = PreferencesDialog(self, self.config_manager, self.sound_manager)
        dialog.run()
        dialog.destroy()

    def on_about(self, widget) -> None:
        """Show about dialog"""
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("Access IRC")
        dialog.set_version("1.0.0")
        dialog.set_comments("An accessible IRC client for Linux with screen reader support")
        dialog.set_website("https://github.com/yourusername/access-irc")
        dialog.set_license_type(Gtk.License.GPL_3_0)
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

        # Add PM to tree (or get existing)
        pm_iter = self.add_pm_to_tree(self.current_server, username)

        # Select the PM in the tree
        if pm_iter:
            selection = self.tree_view.get_selection()
            selection.select_iter(pm_iter)

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
                connection.irc.quote(f"WHOIS {username}")
                self.add_system_message(self.current_server, self.current_target,
                                       f"Sent WHOIS query for {username}")

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
