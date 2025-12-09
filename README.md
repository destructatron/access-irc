# Access IRC

An accessible IRC client for Linux with screen reader support via AT-SPI2.

## Overview

Access IRC is designed specifically for users who rely on screen readers. It provides real-time accessibility announcements through AT-SPI2, full keyboard navigation, and customizable audio notifications.

## Features

### Accessibility
- AT-SPI2 integration for instant screen reader announcements (Orca and others)
- Configurable announcement settings: all messages, mentions only, or custom
- Full keyboard navigation with mnemonics (Alt+key shortcuts)
- Properly labeled form inputs and navigable message history
- Spell checking in message input (requires gspell)

### IRC Functionality
- Multi-server support with autoconnect option
- Channel and private message management
- Common IRC commands: `/join`, `/part`, `/msg`, `/query`, `/nick`, `/topic`, `/whois`, `/kick`, `/mode`, `/away`, `/invite`, `/me`, `/list`, `/quit`, `/raw`, `/exec`
- **Channel list browser**: Search and browse available channels with pagination
- User lists with mode prefixes (@, +, %, ~, &)
- Tab completion for usernames in channels (press Tab to cycle through matches)
- CTCP ACTION and NOTICE support
- SSL/TLS with self-signed certificate support
- IRC bouncer compatibility (ZNC, etc.)
- **Conversation logging**: Per-server logging with date-based rotation
- **Plugin system**: Extend functionality with custom Python scripts (pluggy-based)

### Notifications
- GStreamer-based sound notifications for mentions, messages, joins, parts, and notices
- Persistent JSON configuration
- Customizable sound files

## Installation

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv \
  libgirepository1.0-dev gcc libcairo2-dev pkg-config \
  gir1.2-gtk-3.0 at-spi2-core \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gir1.2-gspell-1 libgspell-1-dev
```

**Fedora:**
```bash
sudo dnf install python3 python3-devel python3-pip \
  gobject-introspection-devel cairo-devel pkg-config gtk3 at-spi2-core gcc \
  gstreamer1-plugins-base gstreamer1-plugins-good \
  gspell-devel
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip \
  gobject-introspection cairo pkgconf gtk3 at-spi2-core base-devel \
  gst-plugins-base gst-plugins-good python-gobject \
  gspell
```

**Gentoo:**
```bash
sudo emerge -av dev-libs/gobject-introspection x11-libs/gtk+ \
  app-accessibility/at-spi2-core dev-util/pkgconfig \
  media-libs/gst-plugins-base media-libs/gst-plugins-good dev-python/pygobject \
  app-text/gspell
```

### Application Setup

```bash
# Clone the repository
git clone https://github.com/destructatron/access-irc.git
cd access-irc

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install the package
pip install -e .

# Generate default sound files (optional, requires numpy and scipy)
python3 scripts/generate_sounds.py

# Run Access IRC
access-irc
```

**Note:** The `-e` flag installs in editable mode, useful for development. For regular installation, use `pip install .` instead.

## Usage

### First Run

1. Start the application: `access-irc`
2. Go to Settings → Preferences → User to set your nickname and real name
3. Go to Server → Manage Servers to add IRC servers
4. Click Connect to join a server

You can also run it as a Python module: `python3 -m access_irc`

### Configuration

Configuration is stored in `config.json` in your current directory (auto-created from the included `config.json.example` on first run):

```json
{
  "nickname": "YourNick",
  "realname": "Your Name",
  "servers": [
    {
      "name": "Libera Chat",
      "host": "irc.libera.chat",
      "port": 6697,
      "ssl": true,
      "verify_ssl": true,
      "channels": ["#python"],
      "username": "",
      "password": "",
      "sasl": false
    }
  ],
  "sounds": {
    "enabled": true,
    "mention": "sounds/mention.wav",
    "message": "sounds/message.wav",
    "notice": "sounds/notice.wav",
    "join": "sounds/join.wav",
    "part": "sounds/part.wav"
  },
  "ui": {
    "announce_all_messages": false,
    "announce_mentions_only": true,
    "announce_joins_parts": false,
    "scrollback_limit": 1000
  },
  "logging": {
    "log_directory": ""
  }
}
```

### Conversation Logging

Access IRC can log all IRC conversations to disk with per-server control:

**Setup:**
1. Go to Settings → Preferences → Chat tab
2. Set a log directory (e.g., `/home/user/irclogs`)
3. Go to Server → Manage Servers, edit each server you want to log
4. Check "Enable logging" for that server

**Log Format:**
```
log_directory/
├── ServerName/
│   ├── #channel-2025-11-29.log
│   ├── #channel-2025-11-30.log
│   └── nickname-2025-11-29.log
```

Each log file contains timestamped messages:
```
[14:32:15] <alice> Hello everyone!
[14:32:20] * bob waves
[14:33:01] --> charlie has joined #channel
```

Logs are automatically rotated daily (new file each day) and organized by server and channel.

### Message Scrollback

Access IRC limits the number of messages kept in memory for each channel and private conversation to prevent excessive memory usage:

- **Default limit**: 1000 messages per channel/PM
- **Configurable**: Go to Settings → Preferences → Chat tab to adjust
- **Range**: 0 (unlimited) to 10,000 messages
- **Behavior**: When the limit is reached, oldest messages are removed from the buffer

Note that this only affects in-memory display. If logging is enabled, all messages are still saved to disk regardless of the scrollback limit.

### Keyboard Navigation

- `Tab` / `Shift+Tab` - Navigate between UI elements (or complete usernames when typing in message input)
- `Alt+S` - Server menu
- `Alt+C` - Channel menu
- `Alt+T` - Settings menu
- `Alt+H` - Help menu
- `Alt+M` - Focus message input
- `Alt+U` - Focus users list (in channels)
- `Ctrl+W` - Close current PM or leave channel
- `Ctrl+S` - Cycle announcement mode (all messages → mentions only → none)
- `F2` - Toggle announcements for current channel only (enabled → disabled → use global setting)
- `Ctrl+Page Up` - Switch to previous channel/buffer
- `Ctrl+Page Down` - Switch to next channel/buffer
- Arrow keys - Navigate message history or tree view
- `Enter` - Send message (in input field)
- `Shift+Enter` - Insert new line in message input (allows multi-line messages)

### IRC Commands

- `/join #channel` - Join a channel
- `/part [reason]` - Leave current channel
- `/msg <nick> <message>` - Send private message
- `/query <nick> [message]` - Start private conversation
- `/nick <newnick>` - Change nickname
- `/topic [new topic]` - View or set channel topic
- `/whois <nick>` - Get user information
- `/kick <nick> [reason]` - Kick user from channel
- `/mode <target> <modes>` - Set channel or user modes
- `/away [message]` - Set away status
- `/invite <nick> [channel]` - Invite user to channel
- `/me <action>` - Send CTCP ACTION
- `/list` - Open channel list browser (see below)
- `/raw <command>` - Send raw IRC command
- `/quit [message]` - Disconnect and quit

### Channel List

The `/list` command opens a dialog to browse and join channels on the current server:

**Features:**
- **Filter/Search**: Type to filter channels by name or topic
- **Pagination**: Browse channels 100 at a time with Previous/Next buttons
- **Sorted by popularity**: Channels are sorted by user count (most popular first)
- **Screen reader announcements**: Previous/Next buttons announce the current range (e.g., "Showing channels 101 to 200 of 4175")

**Usage:**
1. Type `/list` in the message input while connected to a server
2. Wait for the server to send the channel list (a message will confirm when it's ready)
3. Use the Filter field to search for channels by name or topic
4. Navigate with Previous (Alt+P) and Next (Alt+N) buttons
5. Press Enter on a channel to join it

**Accessibility:**
- Filter field has mnemonic Alt+F
- Pagination buttons announce the visible range to screen readers
- Channels display in a table with Channel, Users, and Topic columns
- Status shows current range (e.g., "Showing 1-100 of 500 channels")

### Plugin System

Access IRC supports custom plugins for extending functionality. Plugins can filter messages, add custom commands, respond to IRC events, and more.

**Installation:**
Plugins are Python files placed in `~/.config/access-irc/plugins/`. They are loaded automatically when Access IRC starts.

```bash
# Create the plugins directory
mkdir -p ~/.config/access-irc/plugins

# Copy an example plugin
cp examples/plugins/message_filter.py ~/.config/access-irc/plugins/
```

**Example Plugins:**
The `examples/plugins/` directory contains ready-to-use plugins:

- **message_filter.py** - Filter messages by user, word, or channel:
  - `/filter ignore <nick>` - Block messages from a user
  - `/filter word <word>` - Replace words with asterisks
  - `/filter mute <#channel>` - Mute an entire channel
  - `/filter list` - Show current filters

- **highlight_words.py** - Custom keyword notifications:
  - `/highlight add <word>` - Get announcements when a word appears
  - `/highlight list` - Show highlight words

- **auto_greet.py** - Auto-greet users joining channels:
  - `/greet enable <#channel>` - Enable for a channel
  - `/greet message <text>` - Set custom greeting

**Writing Plugins:**
See `examples/plugins/README.md` for the full plugin API documentation. Basic structure:

```python
from access_irc.plugin_specs import hookimpl

class Plugin:
    @hookimpl
    def on_message(self, ctx, server, target, sender, message, is_mention):
        # React to messages
        pass

    @hookimpl
    def filter_incoming_message(self, ctx, server, target, sender, message):
        # Return {'block': True} to block, {'message': 'new'} to modify
        return None

    @hookimpl
    def on_command(self, ctx, server, target, command, args):
        if command == "mycommand":
            ctx.add_system_message(server, target, "Hello from plugin!")
            return True  # Command handled
        return False
```

## Technology

- **GUI**: GTK 3 via PyGObject
- **IRC**: miniirc
- **Audio**: GStreamer
- **Accessibility**: AT-SPI2
- **Plugins**: pluggy
- **Language**: Python 3.7+

## Architecture

Access IRC uses a manager-based architecture:

- `access_irc/__main__.py` - Application entry point
- `access_irc/gui.py` - GTK 3 interface and AT-SPI2 integration
- `access_irc/irc_manager.py` - IRC connection handling with threading
- `access_irc/config_manager.py` - JSON configuration
- `access_irc/sound_manager.py` - GStreamer audio notifications
- `access_irc/log_manager.py` - Conversation logging to disk
- `access_irc/plugin_manager.py` - Plugin discovery and hook execution
- `access_irc/plugin_specs.py` - Plugin hook specifications
- `access_irc/server_dialog.py` - Server management UI
- `access_irc/preferences_dialog.py` - Preferences UI

See `CLAUDE.md` for detailed development documentation.

### Development Installation

For development, install in editable mode:

```bash
pip install -e .
```

This allows you to make changes to the code without reinstalling the package.

## Troubleshooting

**No sound:**
- Verify GStreamer is working: `python3 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst"`
- Check that sound files exist in `sounds/` directory
- Enable sounds in Settings → Preferences → Sounds

**Screen reader announcements not working:**
- Verify Orca is running: `ps aux | grep orca`
- Check that `at-spi2-core` is installed
- Adjust announcement settings in Preferences → Accessibility

**Import errors:**
- Ensure system dependencies are installed before creating the virtual environment
- Reinstall PyGObject: `pip install --force-reinstall PyGObject`

**Connection failures:**
- Verify hostname and port are correct
- Try toggling SSL on/off
- For self-signed certificates, set `verify_ssl: false` in server config
- Check firewall settings

## Contributing

Contributions are welcome. Please test accessibility features thoroughly and follow the existing code style. See `CLAUDE.md` for development guidelines.
