#!/usr/bin/env python3
"""
Preferences Dialog for Access IRC
Allows configuring user preferences and settings
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import os


class PreferencesDialog(Gtk.Dialog):
    """Dialog for application preferences"""

    def __init__(self, parent, config_manager, sound_manager, log_manager=None):
        """
        Initialize preferences dialog

        Args:
            parent: Parent window
            config_manager: ConfigManager instance
            sound_manager: SoundManager instance
            log_manager: LogManager instance (optional)
        """
        super().__init__(title="Preferences", parent=parent, modal=True)
        self.set_default_size(500, 400)
        self.set_border_width(12)

        self.config = config_manager
        self.sound_manager = sound_manager
        self.log_manager = log_manager

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        self._build_ui()
        self._load_preferences()

        # Connect signals
        self.connect("response", self.on_response)

    def _build_ui(self) -> None:
        """Build dialog UI"""

        box = self.get_content_area()
        box.set_spacing(6)

        # Notebook for different preference categories
        notebook = Gtk.Notebook()
        box.pack_start(notebook, True, True, 0)

        # User Settings tab
        notebook.append_page(self._create_user_tab(), Gtk.Label(label="User"))

        # Chat tab
        notebook.append_page(self._create_chat_tab(), Gtk.Label(label="Chat"))

        # Sounds tab
        notebook.append_page(self._create_sounds_tab(), Gtk.Label(label="Sounds"))

        # Accessibility tab
        notebook.append_page(self._create_accessibility_tab(), Gtk.Label(label="Accessibility"))

        self.show_all()

    def _create_user_tab(self) -> Gtk.Box:
        """Create user settings tab"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        # Grid for form fields
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)
        box.pack_start(grid, False, False, 0)

        row = 0

        # Nickname
        label = Gtk.Label.new_with_mnemonic("_Nickname:")
        label.set_halign(Gtk.Align.END)
        self.nickname_entry = Gtk.Entry()
        label.set_mnemonic_widget(self.nickname_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.nickname_entry, 1, row, 1, 1)
        row += 1

        # Real name
        label = Gtk.Label.new_with_mnemonic("_Real name:")
        label.set_halign(Gtk.Align.END)
        self.realname_entry = Gtk.Entry()
        label.set_mnemonic_widget(self.realname_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.realname_entry, 1, row, 1, 1)
        row += 1

        # Quit message
        label = Gtk.Label.new_with_mnemonic("_Quit message:")
        label.set_halign(Gtk.Align.END)
        self.quit_message_entry = Gtk.Entry()
        self.quit_message_entry.set_placeholder_text("Message shown when disconnecting")
        label.set_mnemonic_widget(self.quit_message_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.quit_message_entry, 1, row, 1, 1)
        row += 1

        return box

    def _create_chat_tab(self) -> Gtk.Box:
        """Create chat settings tab"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        # Display preferences
        label = Gtk.Label(label="<b>Display Preferences</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        # Show timestamps
        self.show_timestamps = Gtk.CheckButton.new_with_mnemonic(
            "Show _timestamps in messages"
        )
        box.pack_start(self.show_timestamps, False, False, 0)

        # Scrollback limit
        scrollback_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        scrollback_label = Gtk.Label.new_with_mnemonic("_Scrollback limit:")
        scrollback_label.set_halign(Gtk.Align.START)
        scrollback_hbox.pack_start(scrollback_label, False, False, 0)

        # SpinButton for scrollback limit (0 to 10000, step 100)
        adjustment = Gtk.Adjustment(value=1000, lower=0, upper=10000, step_increment=100, page_increment=500)
        self.scrollback_spin = Gtk.SpinButton()
        self.scrollback_spin.set_adjustment(adjustment)
        self.scrollback_spin.set_digits(0)
        self.scrollback_spin.set_tooltip_text("Number of messages to keep in history (0 = unlimited)")
        scrollback_label.set_mnemonic_widget(self.scrollback_spin)
        scrollback_hbox.pack_start(self.scrollback_spin, False, False, 0)

        scrollback_info = Gtk.Label(label="messages (0 = unlimited)")
        scrollback_info.set_halign(Gtk.Align.START)
        scrollback_hbox.pack_start(scrollback_info, False, False, 0)

        box.pack_start(scrollback_hbox, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        # Logging preferences
        label = Gtk.Label(label="<b>Logging</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        # Log directory
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        log_label = Gtk.Label.new_with_mnemonic("_Log directory:")
        log_label.set_halign(Gtk.Align.END)
        hbox.pack_start(log_label, False, False, 0)

        self.log_directory_entry = Gtk.Entry()
        self.log_directory_entry.set_placeholder_text("Leave empty to disable logging")
        self.log_directory_entry.set_hexpand(True)
        log_label.set_mnemonic_widget(self.log_directory_entry)
        hbox.pack_start(self.log_directory_entry, True, True, 0)

        browse_btn = Gtk.Button(label="Browse...")
        browse_btn.connect("clicked", self.on_browse_log_directory)
        hbox.pack_start(browse_btn, False, False, 0)

        box.pack_start(hbox, False, False, 0)

        # Info label
        info = Gtk.Label()
        info.set_markup(
            "<i>Note: Enable logging per-server in Server Management.\n"
            "Logs are organized by server and date: log_dir/server/channel-YYYY-MM-DD.log</i>"
        )
        info.set_line_wrap(True)
        info.set_halign(Gtk.Align.START)
        box.pack_start(info, False, False, 0)

        return box

    def _create_sounds_tab(self) -> Gtk.Box:
        """Create sounds settings tab"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        # Enable sounds checkbox
        self.sounds_enabled = Gtk.CheckButton.new_with_mnemonic("_Enable sound notifications")
        box.pack_start(self.sounds_enabled, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        # Sound file paths
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)
        box.pack_start(grid, False, False, 0)

        row = 0

        # Sound types
        self.sound_entries = {}
        for sound_type, label_text in [
            ("mention", "_Mention sound:"),
            ("message", "M_essage sound:"),
            ("privmsg", "_Private message sound:"),
            ("notice", "_Notice sound:"),
            ("join", "_Join sound:"),
            ("part", "_Part sound:"),
            ("quit", "_Quit sound:")
        ]:
            label = Gtk.Label.new_with_mnemonic(label_text)
            label.set_halign(Gtk.Align.END)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            entry = Gtk.Entry()
            entry.set_hexpand(True)
            label.set_mnemonic_widget(entry)

            browse_btn = Gtk.Button(label="Browse...")
            browse_btn.connect("clicked", self.on_browse_sound, entry)

            hbox.pack_start(entry, True, True, 0)
            hbox.pack_start(browse_btn, False, False, 0)

            grid.attach(label, 0, row, 1, 1)
            grid.attach(hbox, 1, row, 1, 1)

            self.sound_entries[sound_type] = entry
            row += 1

        return box

    def _create_accessibility_tab(self) -> Gtk.Box:
        """Create accessibility settings tab"""

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(12)

        # Screen reader announcements
        label = Gtk.Label(label="<b>Screen Reader Announcements</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        # Announce all messages
        self.announce_all = Gtk.RadioButton.new_with_mnemonic_from_widget(
            None, "_Announce all messages"
        )
        box.pack_start(self.announce_all, False, False, 0)

        # Announce mentions only
        self.announce_mentions = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.announce_all, "Announce _mentions only (recommended)"
        )
        box.pack_start(self.announce_mentions, False, False, 0)

        # No announcements
        self.announce_none = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.announce_all, "_No automatic announcements"
        )
        box.pack_start(self.announce_none, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        # Announce joins/parts
        self.announce_joins_parts = Gtk.CheckButton.new_with_mnemonic(
            "Announce _joins and parts"
        )
        box.pack_start(self.announce_joins_parts, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        # Info label
        info = Gtk.Label()
        info.set_markup(
            "<i>Note: Announcements use AT-SPI2 to communicate with screen readers like Orca.\n"
            "Too many announcements can be overwhelming, so 'mentions only' is recommended.</i>"
        )
        info.set_line_wrap(True)
        info.set_halign(Gtk.Align.START)
        box.pack_start(info, False, False, 6)

        return box

    def _load_preferences(self) -> None:
        """Load current preferences"""

        # User settings
        self.nickname_entry.set_text(self.config.get_nickname())
        self.realname_entry.set_text(self.config.get_realname())
        self.quit_message_entry.set_text(self.config.get_quit_message())

        # Sound settings
        self.sounds_enabled.set_active(self.config.are_sounds_enabled())

        for sound_type, entry in self.sound_entries.items():
            path = self.config.get_sound_path(sound_type)
            if path:
                entry.set_text(path)

        # Accessibility settings
        if self.config.should_announce_all_messages():
            self.announce_all.set_active(True)
        elif self.config.should_announce_mentions():
            self.announce_mentions.set_active(True)
        else:
            self.announce_none.set_active(True)

        self.announce_joins_parts.set_active(self.config.should_announce_joins_parts())

        # Display settings
        self.show_timestamps.set_active(self.config.should_show_timestamps())
        self.scrollback_spin.set_value(self.config.get_scrollback_limit())

        # Logging settings
        self.log_directory_entry.set_text(self.config.get_log_directory())

    def _save_preferences(self) -> None:
        """Save preferences"""

        # User settings
        self.config.set_nickname(self.nickname_entry.get_text().strip())
        self.config.set_realname(self.realname_entry.get_text().strip())
        self.config.set_quit_message(self.quit_message_entry.get_text().strip())

        # Sound settings
        self.config.set("sounds", {
            "enabled": self.sounds_enabled.get_active(),
            "mention": self.sound_entries["mention"].get_text(),
            "message": self.sound_entries["message"].get_text(),
            "privmsg": self.sound_entries["privmsg"].get_text(),
            "notice": self.sound_entries["notice"].get_text(),
            "join": self.sound_entries["join"].get_text(),
            "part": self.sound_entries["part"].get_text(),
            "quit": self.sound_entries["quit"].get_text()
        })

        # Accessibility settings
        announce_all = self.announce_all.get_active()
        announce_mentions = self.announce_mentions.get_active()

        self.config.set("ui", {
            "show_timestamps": self.show_timestamps.get_active(),
            "scrollback_limit": int(self.scrollback_spin.get_value()),
            "announce_all_messages": announce_all,
            "announce_mentions_only": announce_mentions,
            "announce_joins_parts": self.announce_joins_parts.get_active()
        })

        # Logging settings
        log_dir = self.log_directory_entry.get_text().strip()
        self.config.set_log_directory(log_dir)

        # Update log manager with new directory if it exists
        if self.log_manager:
            # Get list of connected servers that have logging enabled (thread-safe)
            connected_servers = []
            parent = self.get_transient_for()
            if parent and hasattr(parent, 'irc_manager'):
                irc_mgr = parent.irc_manager
                # Use lock to safely read connections dict
                with irc_mgr._connections_lock:
                    connected_server_names = list(irc_mgr.connections.keys())

                # Filter to only include servers with logging enabled
                for server_name in connected_server_names:
                    for server_config in self.config.get_servers():
                        if server_config.get("name") == server_name:
                            if server_config.get("logging_enabled", False):
                                connected_servers.append(server_name)
                            break

            # Update log directory and create server directories
            try:
                self.log_manager.set_log_directory(log_dir, connected_servers)
            except OSError as e:
                # Show error dialog if directory creation fails
                error_dialog = Gtk.MessageDialog(
                    transient_for=self,
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to create log directories"
                )
                error_dialog.format_secondary_text(str(e))
                error_dialog.run()
                error_dialog.destroy()

        # Save config file
        self.config.save_config()

        # Reload sounds if sound manager exists
        if self.sound_manager:
            self.sound_manager.reload_sounds()

    def on_browse_sound(self, widget, entry: Gtk.Entry) -> None:
        """Browse for sound file"""

        dialog = Gtk.FileChooserDialog(
            title="Choose Sound File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        # Add file filters
        filter_audio = Gtk.FileFilter()
        filter_audio.set_name("Audio files")
        filter_audio.add_mime_type("audio/*")
        dialog.add_filter(filter_audio)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        # Set current folder to sounds directory if it exists
        if os.path.exists("sounds"):
            dialog.set_current_folder(os.path.abspath("sounds"))

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            entry.set_text(filename)

        dialog.destroy()

    def on_browse_log_directory(self, widget) -> None:
        """Browse for log directory"""

        dialog = Gtk.FileChooserDialog(
            title="Choose Log Directory",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        # Set current folder if one is already configured
        current_dir = self.log_directory_entry.get_text().strip()
        if current_dir and os.path.exists(current_dir):
            dialog.set_current_folder(current_dir)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            dirname = dialog.get_filename()
            self.log_directory_entry.set_text(dirname)

        dialog.destroy()

    def on_response(self, dialog, response_id) -> None:
        """Handle dialog response"""

        if response_id in (Gtk.ResponseType.OK, Gtk.ResponseType.APPLY):
            self._save_preferences()

        if response_id == Gtk.ResponseType.APPLY:
            # Prevent dialog from closing on Apply
            self.stop_emission_by_name("response")
        elif response_id == Gtk.ResponseType.OK:
            self.destroy()
