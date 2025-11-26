# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Access IRC is an accessible GTK 3 IRC client for Linux with screen reader support via AT-SPI2. The application is written in Python and specifically designed for visually impaired users who rely on screen readers like Orca.

## Running the Application

```bash
# Run the application
python3 main.py
# or
./main.py

# Generate test sound files (requires numpy and scipy)
python3 generate_sounds.py

# Install dependencies
pip install -r requirements.txt
# or use the installer
./install.sh
```

## Architecture

### Multi-Layer Manager Pattern

The application uses a manager-based architecture where responsibilities are separated into distinct components:

1. **ConfigManager** (`config_manager.py`) - Handles JSON configuration persistence
2. **SoundManager** (`sound_manager.py`) - Manages pygame.mixer for audio notifications
3. **IRCManager** (`irc_manager.py`) - Manages multiple IRC server connections
4. **AccessibleIRCWindow** (`gui.py`) - Main GTK 3 UI with AT-SPI2 integration

All managers are instantiated in `main.py` and injected into the GUI via `set_managers()`.

### IRC Connection Threading Model

**Critical**: The IRC connections run in separate threads (miniirc handles this internally), but GTK must only be updated from the main thread. This is achieved by:

- IRC event handlers (in `irc_manager.py`) use `GLib.idle_add()` to schedule GUI updates
- All callbacks pass through the application layer (`main.py`) which calls GUI methods
- Example flow: IRC thread → GLib.idle_add(callback) → GTK main thread → GUI update

When modifying IRC handlers, ALWAYS use `GLib.idle_add()` before calling any GTK/GUI functions.

### Message Buffer System

The application maintains separate `Gtk.TextBuffer` instances for each server/channel combination:

- Stored in `gui.py:message_buffers` as `Dict[Tuple[server, target], Gtk.TextBuffer]`
- Buffers persist even when switching views, preserving chat history
- Key format: `(server_name, channel_or_target)`

When a user switches channels in the tree view, the appropriate buffer is loaded into the visible TextView.

## AT-SPI2 Accessibility Implementation

**Core Accessibility Feature**: The `announce_to_screen_reader()` method in `gui.py` sends notifications directly to screen readers:

```python
atk_object = self.get_accessible()
atk_object.emit("notification", message)  # Primary method
# Falls back to emit("announcement", message) for older ATK
```

**When to announce**:
- User is mentioned (controlled by `config.should_announce_mentions()`)
- All messages (if `config.should_announce_all_messages()` is enabled)
  - Regular messages: `"{sender} in {target}: {message}"`
  - CTCP ACTION: `"{sender} {action}"`
  - NOTICE: `"Notice from {sender}: {message}"`
- Joins/parts (if `config.should_announce_joins_parts()` is enabled)

**Announcement Formats**:
- Regular messages are announced with sender and channel context
- Actions (/me) are announced as `"{sender} {action}"` for natural flow
- Notices are prefixed with "Notice from" to distinguish from regular messages
- System messages (joins/parts) are announced as complete sentences

GTK 3 does NOT have `gtk_accessible_announce()` - that's GTK 4 only. We must use ATK signal emission.

## Configuration System

Config is stored in `config.json` (created from `config.json.example` on first run). Structure:

```json
{
  "nickname": "...",
  "realname": "...",
  "servers": [
    {
      "name": "ServerName",
      "host": "irc.example.com",
      "port": 6667,
      "ssl": false,
      "verify_ssl": true,
      "channels": ["#channel1"],
      "username": "",
      "password": "",
      "sasl": false
    }
  ],
  "sounds": {/* sound paths */},
  "ui": {
    "announce_all_messages": true,  // Announce all non-mention messages
    "announce_mentions_only": true, // Announce mentions
    "announce_joins_parts": false   // Announce joins/parts
  }
}
```

**Server Configuration Fields**:
- `name`: Display name for the server
- `host`: IRC server hostname
- `port`: Port number (6667 for plain, 6697 for SSL)
- `ssl`: Enable SSL/TLS connection
- `verify_ssl`: Verify SSL certificates (set to `false` for self-signed certs)
- `channels`: List of channels to auto-join (leave empty for bouncers)
- `username`: Authentication username (for bouncers: `username/network`)
- `password`: Server/bouncer password
- `sasl`: Enable SASL authentication (future feature)

**Important**:
- Server configs should NOT include `nickname` or `realname` fields - they automatically inherit from global config
- If a server config has these fields, they override the global config (usually unwanted)
- To announce all messages via AT-SPI2, set BOTH `announce_all_messages` and `announce_mentions_only` to true
- ConfigManager auto-merges with defaults on load, so missing keys won't crash the app
- Changes are saved immediately via `save_config()`

## Dialog Architecture

The application uses two main dialog types:

1. **ServerManagementDialog** (`server_dialog.py`) - Lists servers with add/edit/remove/connect buttons. Contains nested `ServerEditDialog` for editing individual servers.

2. **PreferencesDialog** (`preferences_dialog.py`) - Tabbed notebook with User, Sounds, and Accessibility tabs.

Both dialogs receive manager references (config, sound, irc) and save changes directly via the managers.

## Sound System

GStreamer is used for high-quality sound playback (no downsampling or quality loss). Each sound type gets its own `playbin` element in `SoundManager.__init__()`. The manager checks for file existence and handles missing files gracefully.

Sound files expected in `sounds/`:
- `mention.wav` - High priority (when user is mentioned)
- `message.wav` - New message received
- `notice.wav` - IRC NOTICE messages (from services, bots, server)
- `join.wav` - User joins channel
- `part.wav` - User leaves channel

Users can specify custom paths in Preferences, and `reload_sounds()` will reload them.

**Sound Playback**:
- Regular messages and /me actions play the `message` sound
- NOTICE messages play the dedicated `notice` sound
- Mentions play the `mention` sound (higher priority)
- Join/part events play their respective sounds

## IRC Protocol Notes

- **miniirc** is used for IRC protocol handling (not irc3 or pydle)
- Each server gets an `IRCConnection` instance with its own miniirc.IRC object
- IRC handlers are registered via `self.irc.Handler(event, colon=False)(handler_function)` inside `_register_handlers()`
  - Handlers must be plain functions (not decorated) with signature: `def handler(irc, hostmask, args)`
  - All handlers must use `GLib.idle_add()` with a wrapper that returns `False` to prevent repeated calls
- Nickname mentions are detected by checking if `self.nickname.lower() in message.lower()`
- To disconnect: Use `self.irc.quote("QUIT :reason")` followed by `self.irc.disconnect()` (miniirc doesn't have a `quit()` method)

### Authentication and SSL

**Server Password Authentication** (for bouncers like ZNC):
- Use the `server_password` parameter in `miniirc.IRC()` to send the PASS command
- Format for ZNC: `username:password` or `username/network:password`
- Example: `server_password="myuser/libera:mypassword"`
- This sends `PASS username/network:password` before NICK/USER commands

**SSL Certificate Verification**:
- Use the `verify_ssl` parameter in `miniirc.IRC()` to control certificate verification
- Set to `False` to accept self-signed certificates (e.g., self-hosted bouncers)
- Default is `True` for security
- miniirc will emit a warning when `verify_ssl=False` is used

### Bouncer Support (ZNC, etc.)

The application supports IRC bouncers with the following features:

**Channel Detection**:
- Bouncers often don't send JOIN messages when connecting
- Instead, they send NAMES replies (353) followed by end-of-names (366)
- The `on_endofnames` handler (366) detects channels from the NAMES list
- When a 366 is received for a channel not in `current_channels`, it triggers a simulated JOIN event
- This adds the channel to the tree view even without explicit JOIN messages

**Authentication Flow**:
1. Client sends `PASS username/network:password` (via `server_password`)
2. Client sends `NICK` and `USER` commands
3. Bouncer authenticates and replays buffer
4. NAMES replies (353) populate user lists for each channel
5. End-of-NAMES (366) triggers channel tree population

**Configuration Tips**:
- Leave `channels` array empty for bouncer connections (bouncer manages channels)
- Use `username/network` format for multi-network bouncers like ZNC
- Set `verify_ssl: false` if using self-signed certificates
- Port 6697 is standard for SSL connections

### IRC Message Types and Commands

**Message Display Formats**:
- Regular messages: `[timestamp] <sender> message`
- CTCP ACTION (/me): `[timestamp] * sender action`
- NOTICE messages: `[timestamp] -sender- message`
- System messages: `[timestamp] * message`

**Supported IRC Commands** (in `gui.py:_handle_command()`):
- `/join #channel` - Join a channel
- `/part` or `/leave [reason]` - Leave current channel
- `/me action` - Send CTCP ACTION message
- `/quit` - Disconnect and exit application

**IRC Event Handlers** (in `irc_manager.py`):
- `PRIVMSG` - Regular messages and CTCP ACTION
  - Detects `\x01ACTION text\x01` format for /me messages
  - Separates actions from regular messages via different callbacks
- `NOTICE` - Server notices, service messages (NickServ, ChanServ, etc.)
- `JOIN`, `PART`, `QUIT`, `NICK`, `KICK` - Channel membership events
- `353` (RPL_NAMREPLY) - User list for channels
- `366` (RPL_ENDOFNAMES) - End of NAMES list (triggers channel detection)

**User List Features**:
- Mode prefixes are preserved and displayed: `@` (op), `+` (voice), `%` (halfop), `~` (owner), `&` (admin)
- Users are sorted alphabetically with prefixes
- List updates on JOIN, PART, QUIT, NICK, KICK events
- Accessible via Tab navigation (treated as single focusable unit)

## Development Guidelines

### Adding New IRC Commands

1. Add command parsing in `gui.py:_handle_command()`
2. Call appropriate `irc_manager` method
3. Add system message feedback for user confirmation

### Adding New Accessibility Announcements

1. Call `self.window.announce_to_screen_reader(message)` from `main.py` callbacks
2. Check config preferences before announcing: `config.should_announce_**()`
3. Keep announcements concise - screen readers read them immediately

### Modifying IRC Event Handlers

- All handlers in `irc_manager.py:_register_handlers()` must use `GLib.idle_add()`
- Pass all necessary data as arguments to the callback
- Do NOT store mutable GTK objects in IRC threads

### GTK Widget Accessibility

When adding new input widgets:
```python
label = Gtk.Label.new_with_mnemonic("_Label:")
entry = Gtk.Entry()
label.set_mnemonic_widget(entry)  # Critical for screen readers
```

This creates keyboard shortcuts (Alt+L) and proper accessibility labeling.

**Menu Items**: Always use `Gtk.MenuItem.new_with_mnemonic()` for menu items to enable keyboard shortcuts:
```python
menu_item = Gtk.MenuItem.new_with_mnemonic("_Connect to Server...")
```
The underscore before a letter creates a mnemonic (keyboard shortcut). This is essential for screen reader users to access menus without mouse or flat review mode.

**TextView Accessibility**: The main message view is set to:
- `set_editable(False)` - Prevents typing in the message history
- `set_cursor_visible(True)` - Allows arrow key navigation for screen readers
This combination makes the text read-only but fully navigable, which is essential for screen reader users to browse message history.

## Testing Accessibility

1. Start Orca: `orca`
2. Run Access IRC: `python3 main.py`
3. Use Tab to navigate, verify Orca reads labels
4. Connect to a test IRC server
5. Have someone mention your nick, verify announcement is spoken immediately
6. Check Preferences → Accessibility to test different announcement modes

## Common Pitfalls

1. **Threading**: Never call GTK methods directly from IRC callbacks - always use GLib.idle_add()
2. **Buffer Management**: Don't forget to create new buffers for new server/channel combinations
3. **AT-SPI2 Signals**: Use "notification" not "announce" (GTK 3 limitation)
4. **Config Persistence**: Call `config.save_config()` after making changes
5. **Mnemonics**: All form labels should use `new_with_mnemonic()` and `set_mnemonic_widget()`

## System Dependencies

This application requires system packages that cannot be installed via pip:
- `python3-gi` (PyGObject)
- `gir1.2-gtk-3.0` (GTK 3 introspection)
- `at-spi2-core` (Accessibility infrastructure)

These must be installed via system package manager before running. See README for distro-specific commands.
