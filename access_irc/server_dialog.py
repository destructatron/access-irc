#!/usr/bin/env python3
"""
Server Management Dialog for Access IRC
Allows adding, editing, and removing servers
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from typing import Optional, Dict, Any


class ServerManagementDialog(Gtk.Dialog):
    """Dialog for managing IRC servers"""

    def __init__(self, parent, config_manager, irc_manager):
        """
        Initialize server management dialog

        Args:
            parent: Parent window
            config_manager: ConfigManager instance
            irc_manager: IRCManager instance
        """
        super().__init__(title="Manage Servers", parent=parent, modal=True)
        self.set_default_size(600, 400)
        self.set_border_width(12)

        self.config = config_manager
        self.irc_manager = irc_manager

        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        # Build UI
        self._build_ui()

        # Load servers
        self._load_servers()

    def _build_ui(self) -> None:
        """Build dialog UI"""

        box = self.get_content_area()
        box.set_spacing(6)

        # Horizontal box for list and buttons
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(hbox, True, True, 0)

        # Left: Server list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        hbox.pack_start(scrolled, True, True, 0)

        # ListStore: name, host, port, ssl, channels (joined), data
        self.store = Gtk.ListStore(str, str, int, bool, str, object)
        self.tree_view = Gtk.TreeView(model=self.store)

        # Columns
        columns = [
            ("Name", 0),
            ("Host", 1),
            ("Port", 2),
            ("SSL", 3),
            ("Channels", 4)
        ]

        for title, col_id in columns:
            if col_id == 3:  # SSL column (boolean)
                renderer = Gtk.CellRendererToggle()
                renderer.set_property("sensitive", False)
                column = Gtk.TreeViewColumn(title, renderer, active=col_id)
            else:
                renderer = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(title, renderer, text=col_id)

            self.tree_view.append_column(column)

        scrolled.add(self.tree_view)

        # Right: Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hbox.pack_start(button_box, False, False, 0)

        # Add button
        add_btn = Gtk.Button(label="Add Server")
        add_btn.connect("clicked", self.on_add_server)
        button_box.pack_start(add_btn, False, False, 0)

        # Edit button
        edit_btn = Gtk.Button(label="Edit Server")
        edit_btn.connect("clicked", self.on_edit_server)
        button_box.pack_start(edit_btn, False, False, 0)

        # Remove button
        remove_btn = Gtk.Button(label="Remove Server")
        remove_btn.connect("clicked", self.on_remove_server)
        button_box.pack_start(remove_btn, False, False, 0)

        button_box.pack_start(Gtk.Separator(), False, False, 6)

        # Connect button
        connect_btn = Gtk.Button(label="Connect")
        connect_btn.connect("clicked", self.on_connect)
        button_box.pack_start(connect_btn, False, False, 0)

        # Disconnect button
        disconnect_btn = Gtk.Button(label="Disconnect")
        disconnect_btn.connect("clicked", self.on_disconnect)
        button_box.pack_start(disconnect_btn, False, False, 0)

        self.show_all()

    def _load_servers(self) -> None:
        """Load servers from config"""
        self.store.clear()

        for server in self.config.get_servers():
            name = server.get("name", "Unknown")
            host = server.get("host", "")
            port = server.get("port", 6667)
            ssl = server.get("ssl", False)
            channels = ", ".join(server.get("channels", []))

            self.store.append([name, host, port, ssl, channels, server])

    def on_add_server(self, widget) -> None:
        """Show add server dialog"""
        dialog = ServerEditDialog(self, None)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            server = dialog.get_server_data()
            self.config.add_server(server)
            self._load_servers()

        dialog.destroy()

    def on_edit_server(self, widget) -> None:
        """Show edit server dialog"""
        selection = self.tree_view.get_selection()
        model, iter = selection.get_selected()

        if not iter:
            return

        server = model.get_value(iter, 5)
        index = model.get_path(iter).get_indices()[0]

        dialog = ServerEditDialog(self, server)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            updated_server = dialog.get_server_data()
            self.config.update_server(index, updated_server)
            self._load_servers()

        dialog.destroy()

    def on_remove_server(self, widget) -> None:
        """Remove selected server"""
        selection = self.tree_view.get_selection()
        model, iter = selection.get_selected()

        if not iter:
            return

        server_name = model.get_value(iter, 0)
        index = model.get_path(iter).get_indices()[0]

        # Confirm removal
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove server '{server_name}'?"
        )
        dialog.format_secondary_text("This will disconnect from the server if connected.")

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            # Disconnect if connected
            if self.irc_manager.is_connected(server_name):
                self.irc_manager.disconnect_server(server_name)

            # Remove from config
            self.config.remove_server(index)
            self._load_servers()

    def on_connect(self, widget) -> None:
        """Connect to selected server"""
        selection = self.tree_view.get_selection()
        model, iter = selection.get_selected()

        if not iter:
            return

        server = model.get_value(iter, 5)
        server_name = server.get("name")

        if self.irc_manager.is_connected(server_name):
            self._show_message("Already connected", f"Already connected to {server_name}")
            return

        if self.irc_manager.connect_server(server):
            # Add server to tree in main window
            parent = self.get_transient_for()
            if parent and hasattr(parent, 'add_server_to_tree'):
                parent.add_server_to_tree(server_name)
                parent.update_status(f"Connecting to {server_name}...")
        else:
            self._show_message("Connection failed", f"Failed to connect to {server_name}")

    def on_disconnect(self, widget) -> None:
        """Disconnect from selected server"""
        selection = self.tree_view.get_selection()
        model, iter = selection.get_selected()

        if not iter:
            return

        server = model.get_value(iter, 5)
        server_name = server.get("name")

        if not self.irc_manager.is_connected(server_name):
            self._show_message("Not connected", f"Not connected to {server_name}")
            return

        self.irc_manager.disconnect_server(server_name)

        # Remove from tree in main window
        parent = self.get_transient_for()
        if parent and hasattr(parent, 'remove_server_from_tree'):
            parent.remove_server_from_tree(server_name)
            parent.update_status(f"Disconnected from {server_name}")

    def _show_message(self, title: str, message: str) -> None:
        """Show message dialog"""
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


class ServerEditDialog(Gtk.Dialog):
    """Dialog for adding/editing a server"""

    def __init__(self, parent, server: Optional[Dict[str, Any]] = None):
        """
        Initialize server edit dialog

        Args:
            parent: Parent window
            server: Server data (None for new server)
        """
        title = "Edit Server" if server else "Add Server"
        super().__init__(title=title, parent=parent, modal=True)
        self.set_border_width(12)

        self.server = server

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        self._build_ui()

        if server:
            self._load_server_data()

    def _build_ui(self) -> None:
        """Build dialog UI"""

        box = self.get_content_area()
        box.set_spacing(12)

        # Grid for form fields
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)
        box.pack_start(grid, True, True, 0)

        row = 0

        # Server name
        label = Gtk.Label.new_with_mnemonic("_Name:")
        label.set_halign(Gtk.Align.END)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("My IRC Server")
        label.set_mnemonic_widget(self.name_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.name_entry, 1, row, 1, 1)
        row += 1

        # Host
        label = Gtk.Label.new_with_mnemonic("_Host:")
        label.set_halign(Gtk.Align.END)
        self.host_entry = Gtk.Entry()
        self.host_entry.set_placeholder_text("irc.example.com")
        label.set_mnemonic_widget(self.host_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.host_entry, 1, row, 1, 1)
        row += 1

        # Port
        label = Gtk.Label.new_with_mnemonic("_Port:")
        label.set_halign(Gtk.Align.END)
        self.port_spin = Gtk.SpinButton()
        self.port_spin.set_range(1, 65535)
        self.port_spin.set_increments(1, 100)
        self.port_spin.set_value(6667)
        label.set_mnemonic_widget(self.port_spin)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.port_spin, 1, row, 1, 1)
        row += 1

        # SSL
        self.ssl_check = Gtk.CheckButton.new_with_mnemonic("Use _SSL/TLS")
        grid.attach(self.ssl_check, 1, row, 1, 1)
        row += 1

        # Verify SSL
        self.verify_ssl_check = Gtk.CheckButton.new_with_mnemonic("_Verify SSL certificates")
        self.verify_ssl_check.set_active(True)  # Default to verified
        self.verify_ssl_check.set_tooltip_text("Disable this for self-signed certificates")
        grid.attach(self.verify_ssl_check, 1, row, 1, 1)
        row += 1

        # Channels
        label = Gtk.Label.new_with_mnemonic("_Channels (comma-separated):")
        label.set_halign(Gtk.Align.END)
        self.channels_entry = Gtk.Entry()
        self.channels_entry.set_placeholder_text("#channel1, #channel2")
        label.set_mnemonic_widget(self.channels_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.channels_entry, 1, row, 1, 1)
        row += 1

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(separator, 0, row, 2, 1)
        row += 1

        # Authentication header
        auth_label = Gtk.Label()
        auth_label.set_markup("<b>Authentication (for bouncers like ZNC)</b>")
        auth_label.set_halign(Gtk.Align.START)
        grid.attach(auth_label, 0, row, 2, 1)
        row += 1

        # Username
        label = Gtk.Label.new_with_mnemonic("_Username:")
        label.set_halign(Gtk.Align.END)
        self.username_entry = Gtk.Entry()
        self.username_entry.set_placeholder_text("username or username/network for ZNC")
        label.set_mnemonic_widget(self.username_entry)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(self.username_entry, 1, row, 1, 1)
        row += 1

        # Password
        label = Gtk.Label.new_with_mnemonic("Pass_word:")
        label.set_halign(Gtk.Align.END)
        password_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)  # Hide password
        self.password_entry.set_placeholder_text("Server/bouncer password")
        label.set_mnemonic_widget(self.password_entry)
        password_hbox.pack_start(self.password_entry, True, True, 0)

        # Show password toggle
        show_password_check = Gtk.CheckButton.new_with_mnemonic("_Show password")
        show_password_check.connect("toggled", lambda w:
            self.password_entry.set_visibility(w.get_active()))
        password_hbox.pack_start(show_password_check, False, False, 0)

        grid.attach(label, 0, row, 1, 1)
        grid.attach(password_hbox, 1, row, 1, 1)
        row += 1

        # SASL
        self.sasl_check = Gtk.CheckButton.new_with_mnemonic("Use _SASL authentication")
        grid.attach(self.sasl_check, 1, row, 1, 1)
        row += 1

        self.show_all()

    def _load_server_data(self) -> None:
        """Load server data into form"""
        if not self.server:
            return

        self.name_entry.set_text(self.server.get("name", ""))
        self.host_entry.set_text(self.server.get("host", ""))
        self.port_spin.set_value(self.server.get("port", 6667))
        self.ssl_check.set_active(self.server.get("ssl", False))
        self.verify_ssl_check.set_active(self.server.get("verify_ssl", True))

        channels = self.server.get("channels", [])
        self.channels_entry.set_text(", ".join(channels))

        # Authentication fields
        self.username_entry.set_text(self.server.get("username", ""))
        self.password_entry.set_text(self.server.get("password", ""))
        self.sasl_check.set_active(self.server.get("sasl", False))

    def get_server_data(self) -> Dict[str, Any]:
        """
        Get server data from form

        Returns:
            Server configuration dict
        """
        # Parse channels
        channels_text = self.channels_entry.get_text()
        channels = [ch.strip() for ch in channels_text.split(",") if ch.strip()]

        # Ensure channels start with #
        channels = [ch if ch.startswith("#") else f"#{ch}" for ch in channels]

        return {
            "name": self.name_entry.get_text().strip(),
            "host": self.host_entry.get_text().strip(),
            "port": int(self.port_spin.get_value()),
            "ssl": self.ssl_check.get_active(),
            "verify_ssl": self.verify_ssl_check.get_active(),
            "channels": channels,
            "username": self.username_entry.get_text().strip(),
            "password": self.password_entry.get_text(),  # Don't strip password
            "sasl": self.sasl_check.get_active()
        }
