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

### IRC Functionality
- Multi-server support
- Channel and private message management
- Common IRC commands: `/join`, `/part`, `/msg`, `/query`, `/nick`, `/topic`, `/whois`, `/kick`, `/mode`, `/away`, `/invite`, `/me`, `/quit`, `/raw`
- User lists with mode prefixes (@, +, %, ~, &)
- CTCP ACTION and NOTICE support
- SSL/TLS with self-signed certificate support
- IRC bouncer compatibility (ZNC, etc.)

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
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

**Fedora:**
```bash
sudo dnf install python3 python3-pip \
  gobject-introspection-devel cairo-devel pkg-config gtk3 at-spi2-core gcc \
  gstreamer1-plugins-base gstreamer1-plugins-good
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip \
  gobject-introspection cairo pkgconf gtk3 at-spi2-core base-devel \
  gst-plugins-base gst-plugins-good python-gobject
```

**Gentoo:**
```bash
sudo emerge -av dev-libs/gobject-introspection x11-libs/gtk+ \
  app-accessibility/at-spi2-core dev-util/pkgconfig \
  media-libs/gst-plugins-base media-libs/gst-plugins-good dev-python/pygobject
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
    "announce_joins_parts": false
  }
}
```

### Keyboard Navigation

- `Tab` / `Shift+Tab` - Navigate between UI elements
- `Alt+S` - Server menu
- `Alt+C` - Channel menu
- `Alt+T` - Settings menu
- `Alt+H` - Help menu
- `Alt+M` - Focus message input
- `Alt+U` - Focus users list (in channels)
- `Ctrl+W` - Close current PM or leave channel
- Arrow keys - Navigate message history or tree view
- `Enter` - Send message (in input field)

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
- `/raw <command>` - Send raw IRC command
- `/quit [message]` - Disconnect and quit

## Technology

- **GUI**: GTK 3 via PyGObject
- **IRC**: miniirc
- **Audio**: GStreamer
- **Accessibility**: AT-SPI2
- **Language**: Python 3.7+

## Architecture

Access IRC uses a manager-based architecture:

- `access_irc/__main__.py` - Application entry point
- `access_irc/gui.py` - GTK 3 interface and AT-SPI2 integration
- `access_irc/irc_manager.py` - IRC connection handling with threading
- `access_irc/config_manager.py` - JSON configuration
- `access_irc/sound_manager.py` - GStreamer audio notifications
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

## License

GNU General Public License v3.0 (GPL-3.0)
