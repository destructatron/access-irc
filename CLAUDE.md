# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Access IRC is an accessible GTK 3 IRC client for Linux with screen reader support via AT-SPI2. The application is written in Python and specifically designed for visually impaired users who rely on screen readers like Orca.

## Running the Application

```bash
# Run the application (as a package)
python3 -m access_irc

# Install dependencies
pip install -r requirements.txt
```

## Testing

The project uses pytest for unit testing. Tests are located in the `tests/` directory.

### Running Tests

```bash
# Run all tests
python3 -m pytest

# Run with verbose output
python3 -m pytest -v

# Run a specific test file
python3 -m pytest tests/test_irc_handling.py

# Run tests matching a pattern
python3 -m pytest -k test_alternate
```

### Test Organization

- `tests/test_config_manager.py` - Configuration persistence, server operations, alternate nicks
- `tests/test_irc_handling.py` - IRC formatting, message splitting, mode changes, topic handling, alternate nick fallback
- `tests/test_irc_helpers.py` - Auto-commands normalization, message length calculation, UTF-8 handling
- `tests/test_logging.py` - Log file creation, path sanitization, logging enable/disable
- `tests/test_plugin_system.py` - Plugin discovery and hook execution

### Testing Patterns

**Mocking GLib.idle_add**: Tests use `monkeypatch` to replace `GLib.idle_add` with a synchronous function to avoid threading issues:
```python
monkeypatch.setattr(
    irc_manager.GLib,
    "idle_add",
    lambda func, *args, **kwargs: func(*args)
)
```

**FakeIRC Objects**: IRC tests use a `FakeIRC` class that captures commands via `quote()` and stores handlers:
```python
class FakeIRC:
    def __init__(self, nick="IRCUser"):
        self.handlers = {}
        self.quoted = []
```

**Temporary Directories**: File I/O tests use `tmp_path` fixture for isolated testing.

## Architecture

### Multi-Layer Manager Pattern

The application uses a manager-based architecture where responsibilities are separated into distinct components:

1. **ConfigManager** (`access_irc/config_manager.py`) - Handles JSON configuration persistence
2. **SoundManager** (`access_irc/sound_manager.py`) - Manages GStreamer for audio notifications
3. **IRCManager** (`access_irc/irc_manager.py`) - Manages multiple IRC server connections
4. **LogManager** (`access_irc/log_manager.py`) - Manages conversation logging to disk
5. **PluginManager** (`access_irc/plugin_manager.py`) - Discovers, loads, and executes plugins
6. **DCCManager** (`access_irc/dcc_manager.py`) - Manages DCC file transfers
7. **AccessibleIRCWindow** (`access_irc/gui.py`) - Main GTK 3 UI with AT-SPI2 integration

All managers are instantiated in `access_irc/__main__.py` and injected into the GUI via `set_managers()` and `set_plugin_manager()`.

### IRC Connection Threading Model

**Critical**: The IRC connections run in separate threads (miniirc handles this internally), but GTK must only be updated from the main thread. This is achieved by:

- IRC event handlers (in `access_irc/irc_manager.py`) use `GLib.idle_add()` to schedule GUI updates
- All callbacks pass through the application layer (`access_irc/__main__.py`) which calls GUI methods
- Example flow: IRC thread → GLib.idle_add(callback) → GTK main thread → GUI update

When modifying IRC handlers, ALWAYS use `GLib.idle_add()` before calling any GTK/GUI functions.

### Message Buffer System

The application maintains separate `Gtk.TextBuffer` instances for each server/channel combination:

- Stored in `access_irc/gui.py:message_buffers` as `Dict[Tuple[server, target], Gtk.TextBuffer]`
- Buffers persist even when switching views, preserving chat history
- Key format: `(server_name, channel_or_target)`

When a user switches channels in the tree view, the appropriate buffer is loaded into the visible TextView.

### Logging System

The application includes a comprehensive logging system for recording IRC conversations to disk:

**Directory Structure**:
```
log_directory/
├── ServerName1/
│   ├── #channel1-2025-11-29.log
│   ├── #channel1-2025-11-30.log
│   └── #channel2-2025-11-29.log
└── ServerName2/
    └── nickname-2025-11-29.log  (private messages)
```

**Log Format**:
```
[14:32:15] <alice> Hello everyone!
[14:32:20] * bob waves
[14:32:25] -NickServ- You are now identified
[14:33:01] --> charlie has joined #python
[14:33:45] <-- charlie has left #python (Goodbye)
[14:34:12] <-- david has quit (Ping timeout)
[14:35:00] --- alice is now known as alice_afk
[14:36:22] <-! spammer was kicked by moderator (Spam)
```

**Key Features**:
- **Per-server control**: Each server has a `logging_enabled` flag in its config
- **Date-based rotation**: New log file created each day (YYYY-MM-DD format)
- **Thread-safe writes**: Uses `threading.Lock()` to prevent race conditions
- **Automatic directory creation**: Creates `log_dir/server/` on-demand and when log directory is set
- **Secure path sanitization**: Prevents path traversal attacks, removes null bytes, limits filename length
- **All events logged**: Messages, actions, notices, joins, parts, quits, nick changes, kicks

**Configuration** (in `access_irc/__main__.py`):
- LogManager checks `_should_log_server(server_name)` before logging
- This verifies both the log directory is set AND the server has logging enabled
- All IRC event handlers call appropriate `log.*()` methods when logging is enabled

**Thread Safety** (critical):
- LogManager uses `self._write_lock` to protect concurrent file writes
- IRCManager uses `self._connections_lock` to protect the connections dictionary
- When reading connected servers (e.g., in preferences), ALWAYS use the lock:
  ```python
  with irc_manager._connections_lock:
      servers = list(irc_manager.connections.keys())
  ```

**Error Handling**:
- `set_log_directory()` raises `OSError` if directory creation fails
- Preferences dialog catches errors and shows user-friendly error dialogs
- Invalid server names are skipped (empty or whitespace-only)

### Plugin System

The application supports custom plugins via the pluggy framework. Plugins can filter messages, add custom commands, and respond to IRC events.

**Architecture**:
- `access_irc/plugin_specs.py` - Defines hook specifications using `@hookspec` decorator
- `access_irc/plugin_manager.py` - Contains `PluginManager` and `PluginContext` classes
- Plugins are loaded from `~/.config/access-irc/plugins/`

**Plugin Discovery** (in `PluginManager.discover_and_load_plugins()`):
1. Scans `~/.config/access-irc/plugins/` for `.py` files
2. Also loads plugin packages (directories with `__init__.py`)
3. Files starting with `_` are skipped
4. Each plugin is registered with pluggy's `PluginManager`

**Plugin Structure**:
Plugins can use either a `Plugin` class or a `setup()` function:
```python
from access_irc.plugin_specs import hookimpl

class Plugin:
    @hookimpl
    def on_message(self, ctx, server, target, sender, message, is_mention):
        pass

# Or alternatively:
def setup(ctx):
    return MyPluginInstance()
```

**Hook Types**:

1. **Lifecycle Hooks** - Called during application lifecycle:
   - `on_startup(ctx)` - Application started
   - `on_shutdown(ctx)` - Application shutting down
   - `on_connect(ctx, server)` - Connected to server
   - `on_disconnect(ctx, server)` - Disconnected from server

2. **Filter Hooks** - Can block or modify content (use `firstresult=True`):
   - `filter_incoming_message(ctx, server, target, sender, message)`
   - `filter_incoming_action(ctx, server, target, sender, action)`
   - `filter_incoming_notice(ctx, server, target, sender, message)`
   - `filter_outgoing_message(ctx, server, target, message)`

   Return values:
   - `None` - Allow unchanged
   - `{'block': True}` - Block entirely
   - `{'message': 'new text'}` or `{'action': 'new text'}` - Modify content

3. **Event Hooks** - Notification only, cannot modify:
   - `on_message(ctx, server, target, sender, message, is_mention)`
   - `on_action(ctx, server, target, sender, action, is_mention)`
   - `on_notice(ctx, server, target, sender, message)`
   - `on_join(ctx, server, channel, nick)`
   - `on_part(ctx, server, channel, nick, reason)`
   - `on_quit(ctx, server, nick, reason)`
   - `on_nick(ctx, server, old_nick, new_nick)`
   - `on_kick(ctx, server, channel, kicked, kicker, reason)`
   - `on_topic(ctx, server, channel, topic, setter)`

4. **Command Hook** - Handle custom `/commands`:
   - `on_command(ctx, server, target, command, args)` - Return `True` if handled

**PluginContext API** (the `ctx` object passed to hooks):

```python
# IRC Operations
ctx.send_message(server, target, message)
ctx.send_action(server, target, action)
ctx.send_notice(server, target, message)
ctx.send_raw(server, command)
ctx.join_channel(server, channel)
ctx.part_channel(server, channel, reason)

# UI Operations
ctx.add_system_message(server, target, message, announce=False)
ctx.announce(message)  # Screen reader announcement
ctx.play_sound(type)   # 'message', 'mention', 'notice', 'join', 'part'

# Information
ctx.get_current_server()
ctx.get_current_target()
ctx.get_nickname(server)
ctx.get_connected_servers()
ctx.get_channels(server)
ctx.get_config(key, default)  # Supports dot notation: 'ui.announce_all_messages'

# Timers
ctx.add_timer(timer_id, interval_ms, callback)  # Repeating, callback returns bool
ctx.remove_timer(timer_id)
ctx.add_timeout(delay_ms, callback)  # One-shot
```

**Thread Safety**:
- All `ctx` methods that touch GTK use `GLib.idle_add()` internally
- Plugin hooks are called from the main thread (after `GLib.idle_add()` in IRC handlers)
- Plugins should NOT create their own threads that touch GTK

**Hook Execution Flow** (in `access_irc/__main__.py`):
1. IRC event received in IRC thread
2. `GLib.idle_add()` schedules callback on main thread
3. Filter hooks called first (can block/modify)
4. If not blocked, GUI updated and event hooks called
5. Logging and sounds handled

**Error Handling**:
- All hook calls are wrapped in try/except in PluginManager
- Plugin errors are printed to console but don't crash the application
- Individual plugin failures don't affect other plugins

## AT-SPI2 Accessibility Implementation

**Core Accessibility Feature**: The `announce_to_screen_reader()` method in `access_irc/gui.py` sends notifications directly to screen readers:

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

### Spell Checking

The message input uses `pygtkspellcheck` for spell checking:
- Uses `PANGO_UNDERLINE_ERROR` which Orca recognizes for accessibility
- Language is auto-detected from system locale
- Right-click context menu provides spelling suggestions
- Falls back gracefully if `pygtkspellcheck` is not installed

The spell checker is attached to the message input TextView and automatically handles buffer changes when switching channels.

## Configuration System

Config is stored in `config.json` (created from `config.json.example` on first run). Structure:

```json
{
  "nickname": "...",
  "realname": "...",
  "alternate_nicks": ["AltNick1", "AltNick2"],
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
      "sasl": false,
      "auto_connect_commands": ["/mode +i", "/join #secret key"]
    }
  ],
  "sounds": {
    "mention": "sounds/mention.wav",
    "mention_enabled": true,
    "message_enabled": true,
    "notice_enabled": true,
    "join_enabled": true,
    "part_enabled": true,
    "invite_enabled": true
  },
  "ui": {
    "announce_all_messages": true,
    "announce_mentions_only": true,
    "announce_joins_parts": false
  },
  "logging": {
    "log_directory": "/path/to/logs"
  },
  "dcc": {
    "auto_accept": false,
    "download_directory": "~/Downloads",
    "port_range_start": 1024,
    "port_range_end": 65535,
    "external_ip": "",
    "announce_transfers": true
  }
}
```

**Global Configuration Fields**:
- `alternate_nicks`: List of fallback nicknames to try if primary is in use (see Alternate Nickname Fallback below)

**Server Configuration Fields**:
- `name`: Display name for the server
- `host`: IRC server hostname
- `port`: Port number (6667 for plain, 6697 for SSL)
- `ssl`: Enable SSL/TLS connection
- `verify_ssl`: Verify SSL certificates (set to `false` for self-signed certs)
- `channels`: List of channels to auto-join (leave empty for bouncers)
- `username`: Authentication username
  - For SASL (when `sasl: true`): NickServ account username
  - For bouncers (when `sasl: false`): Use format `username/network` for ZNC
- `password`: Authentication password
  - For SASL: NickServ account password
  - For bouncers: Server/bouncer password
- `sasl`: Enable SASL authentication for NickServ
  - Set to `true` for direct IRC server connections with NickServ authentication
  - Set to `false` for bouncer connections (ZNC, etc.)
- `autoconnect`: Automatically connect to this server on startup (default: `false`)
- `logging_enabled`: Enable conversation logging for this server (default: `false`)
  - Requires global `logging.log_directory` to be set
  - Logs are saved to `log_directory/ServerName/channel-YYYY-MM-DD.log`
- `auto_connect_commands`: List of commands to execute after connecting (see Auto-Connect Commands below)

**DCC Configuration Fields** (in `dcc` section):
- `auto_accept`: Automatically accept incoming file transfers (default: `false`)
- `download_directory`: Directory to save received files (default: `~/Downloads`)
- `port_range_start` / `port_range_end`: Port range for DCC listening sockets
- `external_ip`: External IP address for NAT/firewall environments (leave empty for auto-detect)
- `announce_transfers`: Announce DCC transfer events to screen reader (default: `true`)

### Alternate Nickname Fallback

When the primary nickname is unavailable (error 433 "Nickname in use" or 432 "Erroneous nickname"), the client automatically tries alternate nicknames in order:

```json
{
  "nickname": "MyNick",
  "alternate_nicks": ["MyNick_", "MyNick__", "MyNickAlt"]
}
```

**Behavior**:
- Alternate nicks are tried sequentially during initial connection
- Once connected, alternate nicks are NOT tried (prevents mid-session nick changes)
- Invalid/empty entries in the list are filtered out
- If all alternates fail, connection proceeds with whatever nick the server assigns

### Auto-Connect Commands

Per-server commands executed automatically after connecting:

```json
{
  "name": "MyServer",
  "auto_connect_commands": [
    "/mode +i",
    "/join #secret secretkey",
    "/raw OPER admin password"
  ]
}
```

**Supported Command Formats**:
- `/mode <modes>` - Set user modes
- `/join #channel [key]` - Join channels (alternative to `channels` config)
- `/nick <newnick>` - Change nickname after connect
- `/away <message>` - Set away status
- `/raw <command>` - Send raw IRC command
- Any other `/command` supported by the client

**Normalization**:
- Commands are stripped of whitespace
- Empty strings and `None` values are filtered out
- Both string (newline-separated) and list formats are supported

**Important**:
- Server configs should NOT include `nickname` or `realname` fields - they automatically inherit from global config
- If a server config has these fields, they override the global config (usually unwanted)
- To announce all messages via AT-SPI2, set BOTH `announce_all_messages` and `announce_mentions_only` to true
- ConfigManager auto-merges with defaults on load, so missing keys won't crash the app
- Changes are saved immediately via `save_config()`

## Dialog Architecture

The application uses two main dialog types:

1. **ServerManagementDialog** (`access_irc/server_dialog.py`) - Lists servers with add/edit/remove/connect buttons. Contains nested `ServerEditDialog` for editing individual servers.
   - ServerEditDialog includes checkboxes for SSL, autoconnect, and logging

2. **PreferencesDialog** (`access_irc/preferences_dialog.py`) - Tabbed notebook with User, Chat, Sounds, and Accessibility tabs.
   - Chat tab includes log directory configuration with browse button
   - When log directory is changed, server subdirectories are created for connected servers

Both dialogs receive manager references (config, sound, irc, log) and save changes directly via the managers.

## Sound System

GStreamer is used for high-quality sound playback (no downsampling or quality loss). Each sound type gets its own `playbin` element in `SoundManager.__init__()`. The manager checks for file existence and handles missing files gracefully.

Sound files expected in `sounds/`:
- `mention.wav` - High priority (when user is mentioned)
- `message.wav` - New message received
- `notice.wav` - IRC NOTICE messages (from services, bots, server)
- `join.wav` - User joins channel
- `part.wav` - User leaves channel
- `invite.wav` - Channel invitation received
- `dcc_receive_complete.wav` - DCC file receive completed
- `dcc_send_complete.wav` - DCC file send completed

Users can specify custom paths in Preferences, and `reload_sounds()` will reload them.

**Sound Playback**:
- Regular messages and /me actions play the `message` sound
- NOTICE messages play the dedicated `notice` sound
- Mentions play the `mention` sound (higher priority)
- Join/part events play their respective sounds
- Channel invitations play the `invite` sound
- DCC transfer completions play their respective sounds

**Per-Sound Enable/Disable**:
Each sound type can be individually enabled or disabled in config:
```json
"sounds": {
  "mention": "sounds/mention.wav",
  "mention_enabled": true,
  "message_enabled": true,
  "notice_enabled": true,
  "join_enabled": true,
  "part_enabled": true,
  "invite_enabled": true,
  "dcc_receive_complete_enabled": true,
  "dcc_send_complete_enabled": true
}
```
This allows granular control over notifications while preserving custom sound paths.

## IRC Protocol Notes

- **miniirc** is used for IRC protocol handling (not irc3 or pydle)
- Each server gets an `IRCConnection` instance with its own miniirc.IRC object
- IRC handlers are registered via `self.irc.Handler(event, colon=False)(handler_function)` inside `access_irc/irc_manager.py:_register_handlers()`
  - Handlers must be plain functions (not decorated) with signature: `def handler(irc, hostmask, args)`
  - All handlers must use `GLib.idle_add()` with a wrapper that returns `False` to prevent repeated calls
- Nickname mentions are detected by checking if `self.nickname.lower() in message.lower()`
- To disconnect: Use `self.irc.quote("QUIT :reason")` followed by `self.irc.disconnect()` (miniirc doesn't have a `quit()` method)

### Authentication and SSL

The application supports two authentication methods that are **mutually exclusive**:

**SASL Authentication** (for NickServ on direct IRC connections):
- Use the `ns_identity` parameter in `miniirc.IRC()` for SASL/NickServ authentication
- Format: `ns_identity=(username, password)` as a tuple
- Example: `ns_identity=("myuser", "mypassword")`
- Enabled when `sasl: true` in server config
- miniirc automatically adds SASL to IRCv3 capabilities when `ns_identity` is specified
- Best for direct connections to IRC networks with NickServ (Libera.Chat, OFTC, etc.)

**Server Password Authentication** (for bouncers like ZNC):
- Use the `server_password` parameter in `miniirc.IRC()` to send the PASS command
- Format for ZNC: `username:password` or `username/network:password`
- Example: `server_password="myuser/libera:mypassword"`
- Enabled when `sasl: false` in server config
- This sends `PASS username/network:password` before NICK/USER commands
- Best for bouncer connections (ZNC, etc.)

**Important**: Do NOT enable SASL for bouncer connections - use `sasl: false` and provide bouncer credentials in `username`/`password` fields.

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

**Supported IRC Commands** (in `access_irc/gui.py:_handle_command()`):
- `/join #channel [key]` - Join a channel (with optional key)
- `/part` or `/leave [reason]` - Leave current channel
- `/me action` - Send CTCP ACTION message
- `/msg <nick> <message>` - Send private message
- `/notice <target> <message>` - Send notice
- `/nick <newnick>` - Change nickname
- `/topic [newtopic]` - View or set channel topic
- `/mode <modes>` - Set channel or user modes
- `/kick <nick> [reason]` - Kick user from channel
- `/invite <nick> [#channel]` - Invite user to channel
- `/away [message]` - Set or clear away status
- `/raw <command>` - Send raw IRC command
- `/dcc send <nick> [filepath]` - Initiate DCC file transfer
- `/quit [message]` - Disconnect and exit application

**IRC Event Handlers** (in `access_irc/irc_manager.py`):
- `PRIVMSG` - Regular messages and CTCP ACTION
  - Detects `\x01ACTION text\x01` format for /me messages
  - Separates actions from regular messages via different callbacks
- `NOTICE` - Server notices, service messages (NickServ, ChanServ, etc.)
- `JOIN`, `PART`, `QUIT`, `NICK`, `KICK` - Channel membership events
- `INVITE` - Channel invitations from other users
- `MODE` - Channel and user mode changes
- `TOPIC` - Channel topic changes
- `353` (RPL_NAMREPLY) - User list for channels
- `366` (RPL_ENDOFNAMES) - End of NAMES list (triggers channel detection)
- `332` (RPL_TOPIC) - Current channel topic
- `333` (RPL_TOPICWHOTIME) - Topic setter and timestamp
- `324` (RPL_CHANNELMODEIS) - Channel mode reply
- `372` (RPL_MOTD) - Message of the day line
- `375` (RPL_MOTDSTART) - Start of MOTD
- `376` (RPL_ENDOFMOTD) - End of MOTD
- `432` (ERR_ERRONEUSNICKNAME) - Invalid nickname
- `433` (ERR_NICKNAMEINUSE) - Nickname in use (triggers alternate nick fallback)
- `471`-`477` - Channel join errors (full, invite-only, banned, bad key)

**User List Features**:
- Mode prefixes are preserved and displayed: `@` (op), `+` (voice), `%` (halfop), `~` (owner), `&` (admin)
- Users are sorted alphabetically with prefixes
- List updates on JOIN, PART, QUIT, NICK, KICK events
- Accessible via Tab navigation (treated as single focusable unit)

### Topic Handling

Channel topics are automatically requested and displayed:

- Topic is requested on self-join (JOIN event for own nick)
- Topic is also requested on end-of-NAMES (366) for bouncer support
- IRC formatting is stripped from topic text before display
- Topic changes trigger `on_topic` plugin hook

**Event Flow**:
1. User joins channel → client sends `TOPIC #channel`
2. Server replies with 332 (topic text) and 333 (setter info)
3. If no topic, server replies with 331
4. Real-time topic changes come via TOPIC command

### Mode Handling

Channel and user modes are parsed and applied to user lists:

**Mode Parsing**: The `_parse_mode_changes()` method handles mode strings like `+ov alice bob`:
```python
# Returns: [('+', 'o', 'alice'), ('+', 'v', 'bob')]
```

**User Mode Prefixes**:
```python
USER_MODE_PREFIXES = {
    'o': '@',   # Operator
    'v': '+',   # Voice
    'h': '%',   # Half-op
    'q': '~',   # Owner (some networks)
    'a': '&'    # Admin (some networks)
}
```

When modes change, user prefixes in the channel list are updated dynamically. Mode removals (`-o`, `-v`) strip the prefix.

### MOTD Handling

Message of the Day (MOTD) lines are displayed as system messages:
- 375 (RPL_MOTDSTART) marks the beginning
- 372 (RPL_MOTD) contains each MOTD line
- 376 (RPL_ENDOFMOTD) marks the end
- 422 (ERR_NOMOTD) indicates no MOTD is available

MOTD is displayed in the server's main buffer on connect.

### IRC Formatting

The `strip_irc_formatting()` function removes mIRC color codes and formatting:
- Bold (`\x02`), italic (`\x1d`), underline (`\x1f`)
- Color codes (`\x03N,N`)
- Reverse (`\x16`), reset (`\x0f`)

This ensures clean text for screen reader announcements and logging.

## DCC File Transfers

The application supports DCC (Direct Client-to-Client) file transfers via the `DCCManager` class.

### DCC Architecture

**Transfer States** (`DCCTransferState` enum):
- `PENDING` - Waiting for user acceptance
- `CONNECTING` - Establishing connection
- `TRANSFERRING` - Active transfer in progress
- `COMPLETED` - Successfully completed
- `FAILED` - Failed with error
- `CANCELLED` - Cancelled by user

**Transfer Direction** (`DCCTransferDirection` enum):
- `SEND` - Sending file to remote user
- `RECEIVE` - Receiving file from remote user

### DCC Commands

- `/dcc send <nick> [filepath]` - Send a file to user (opens file chooser if no path given)
- Right-click on user in user list → "DCC Send..." option

### DCC Threading Model

DCC transfers run in background threads to avoid blocking the GUI:
- Each transfer gets its own `threading.Thread`
- Progress callbacks use `GLib.idle_add()` to update GUI safely
- `_transfer_lock` protects the transfers dictionary for thread safety
- Socket operations use timeouts to allow cancellation checks

### DCC Protocol

**Receiving Files**:
1. Remote user sends CTCP: `DCC SEND filename ip port filesize`
2. `parse_dcc_ctcp()` creates a `DCCTransfer` object in PENDING state
3. User accepts via `accept_transfer()` or rejects via `reject_transfer()`
4. On accept, client connects to remote IP:port
5. File data is received in 8KB blocks with ACK responses

**Sending Files**:
1. User initiates via `/dcc send nick filepath`
2. Client opens listening socket on configured port range
3. CTCP SEND is sent to remote user with IP, port, and filesize
4. Remote user connects, client sends file in 8KB blocks
5. Transfer completes when all bytes acknowledged

### DCC Security

**Filename Sanitization**:
- Path traversal attempts (`../`) are blocked
- Null bytes and control characters are removed
- Filenames are limited to 200 characters
- Unsafe characters are replaced with underscores

**Unique Filenames**: If a file already exists in download directory, a numeric suffix is added (e.g., `file_1.txt`, `file_2.txt`).

### DCC Configuration

See the `dcc` section in Configuration System above for all DCC-related settings.

## Development Guidelines

### Adding Logging to New Events

When adding logging for a new IRC event type:

1. **Add method to LogManager** (`access_irc/log_manager.py`):
   ```python
   def log_new_event(self, server: str, target: str, arg1: str, arg2: str) -> None:
       timestamp = datetime.now().strftime("[%H:%M:%S]")
       line = f"{timestamp} [format your log line here]"
       self._write_to_log(server, target, line)
   ```

2. **Call from event handler** (`access_irc/__main__.py`):
   ```python
   def on_irc_new_event(self, server: str, ...):
       # ... existing GUI code ...

       # Log event if enabled for this server
       if self._should_log_server(server):
           self.log.log_new_event(server, target, arg1, arg2)
   ```

3. **Thread safety**: All log writes are automatically protected by `_write_lock` in `_write_to_log()`

### Adding New IRC Commands

1. Add command parsing in `access_irc/gui.py:_handle_command()`
2. Call appropriate `irc_manager` method
3. Add system message feedback for user confirmation

Note: Plugin commands are checked first via `plugin_manager.call_command()`. Built-in commands take precedence only if no plugin handles the command.

### Adding New Plugin Hooks

To add a new hook that plugins can implement:

1. **Define the hook spec** in `access_irc/plugin_specs.py`:
   ```python
   @hookspec
   def on_new_event(self, ctx, server, arg1, arg2):
       """Document what this hook does and when it's called."""
       pass
   ```

2. **Add caller method** in `access_irc/plugin_manager.py`:
   ```python
   def call_new_event(self, server: str, arg1: str, arg2: str) -> None:
       """Call on_new_event hooks."""
       if self.pm and self.ctx:
           try:
               self.pm.hook.on_new_event(ctx=self.ctx, server=server, arg1=arg1, arg2=arg2)
           except Exception as e:
               print(f"Plugin error in on_new_event: {e}")
   ```

3. **Call from event handler** in `access_irc/__main__.py`:
   ```python
   def on_irc_new_event(self, server: str, ...):
       # ... existing code ...
       self.plugins.call_new_event(server, arg1, arg2)
   ```

For filter hooks (that can block/modify), use `@hookspec(firstresult=True)` and return the filter result to the caller.

### Writing Example Plugins

When creating example plugins in `examples/plugins/`:

1. Include docstring explaining what the plugin does
2. Implement `on_startup` to show a loaded message
3. Use `on_command` for user-facing commands with help text
4. Handle errors gracefully (don't crash on bad input)
5. Document commands in the plugin's docstring

### Adding New Accessibility Announcements

1. Call `self.window.announce_to_screen_reader(message)` from `access_irc/__main__.py` callbacks
2. Check config preferences before announcing: `config.should_announce_**()`
3. Keep announcements concise - screen readers read them immediately

### Modifying IRC Event Handlers

- All handlers in `access_irc/irc_manager.py:_register_handlers()` must use `GLib.idle_add()`
- Pass all necessary data as arguments to the callback
- Do NOT store mutable GTK objects in IRC threads

### Writing Tests

When adding new functionality, create corresponding tests in `tests/`:

1. **Create test file** if needed (e.g., `tests/test_new_feature.py`)
2. **Mock GLib.idle_add** for any code that schedules GUI callbacks:
   ```python
   def test_something(monkeypatch):
       monkeypatch.setattr(
           module.GLib,
           "idle_add",
           lambda func, *args, **kwargs: func(*args)
       )
   ```
3. **Use FakeIRC** for IRC connection tests (see `tests/test_irc_handling.py`)
4. **Use tmp_path** fixture for file I/O tests
5. **Run tests** with `python3 -m pytest -v` to verify

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
2. Run Access IRC: `python3 -m access_irc`
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
6. **Thread-Safe Dictionary Access**: When reading `irc_manager.connections`, use `_connections_lock`:
   ```python
   with irc_manager._connections_lock:
       servers = list(irc_manager.connections.keys())
   ```
7. **Logging**: Check both log directory is set AND server has logging enabled before logging
8. **Path Security**: Always sanitize server/channel names before using in file paths (LogManager handles this)
9. **Plugin Threading**: Plugin hooks are called on the main thread; `ctx` methods handle `GLib.idle_add()` internally
10. **Plugin Errors**: Always wrap plugin hook calls in try/except to prevent one bad plugin from crashing the app
11. **Filter Hook Order**: Filter hooks use `firstresult=True`, so only the first plugin to return non-None wins

## System Dependencies

This application requires system packages that cannot be installed via pip:
- `python3-gi` (PyGObject)
- `gir1.2-gtk-3.0` (GTK 3 introspection)
- `at-spi2-core` (Accessibility infrastructure)

These must be installed via system package manager before running. See README for distro-specific commands.
