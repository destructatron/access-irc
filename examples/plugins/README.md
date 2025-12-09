# Access IRC Example Plugins

This directory contains example plugins for Access IRC. To use a plugin,
copy it to `~/.config/access-irc/plugins/`.

## Available Examples

### message_filter.py
A comprehensive message filtering plugin that can:
- Ignore messages from specific users (`/filter ignore <nick>`)
- Filter out specific words (`/filter word <word>`)
- Mute entire channels (`/filter mute <#channel>`)

### auto_greet.py
Automatically greets users when they join channels:
- Enable for specific channels (`/greet enable <#channel>`)
- Customize the greeting message (`/greet message <text>`)

### highlight_words.py
Get screen reader announcements for custom keywords (beyond your nick):
- Add highlight words (`/highlight add <word>`)
- Plays the mention sound when triggered

## Writing Your Own Plugins

Plugins are Python files that define hook implementations. The simplest
plugin structure is:

```python
from access_irc.plugin_specs import hookimpl

class Plugin:
    @hookimpl
    def on_message(self, ctx, server, target, sender, message, is_mention):
        # Do something with the message
        pass
```

### Available Hooks

**Lifecycle:**
- `on_startup(ctx)` - Called when Access IRC starts
- `on_shutdown(ctx)` - Called when Access IRC exits
- `on_connect(ctx, server)` - Connected to a server
- `on_disconnect(ctx, server)` - Disconnected from a server

**Message Filters (can block/modify):**
- `filter_incoming_message(ctx, server, target, sender, message)`
- `filter_incoming_action(ctx, server, target, sender, action)`
- `filter_incoming_notice(ctx, server, target, sender, message)`
- `filter_outgoing_message(ctx, server, target, message)`

Return `{'block': True}` to block, `{'message': 'new'}` to modify.

**Event Notifications (read-only):**
- `on_message(ctx, server, target, sender, message, is_mention)`
- `on_action(ctx, server, target, sender, action, is_mention)`
- `on_notice(ctx, server, target, sender, message)`
- `on_join(ctx, server, channel, nick)`
- `on_part(ctx, server, channel, nick, reason)`
- `on_quit(ctx, server, nick, reason)`
- `on_nick(ctx, server, old_nick, new_nick)`
- `on_kick(ctx, server, channel, kicked, kicker, reason)`

**Custom Commands:**
- `on_command(ctx, server, target, command, args)` - Return True if handled

### Plugin Context (ctx)

The context object provides these methods:

**Sending:**
- `ctx.send_message(server, target, message)`
- `ctx.send_action(server, target, action)`
- `ctx.send_notice(server, target, message)`
- `ctx.send_raw(server, command)`
- `ctx.join_channel(server, channel)`
- `ctx.part_channel(server, channel, reason)`

**UI:**
- `ctx.add_system_message(server, target, message, announce=False)`
- `ctx.announce(message)` - Screen reader announcement
- `ctx.play_sound(type)` - 'message', 'mention', 'notice', 'join', 'part'

**Information:**
- `ctx.get_current_server()`
- `ctx.get_current_target()`
- `ctx.get_nickname(server)`
- `ctx.get_connected_servers()`
- `ctx.get_channels(server)`
- `ctx.get_config(key, default)`

**Timers:**
- `ctx.add_timer(id, interval_ms, callback)` - Repeating timer
- `ctx.remove_timer(id)`
- `ctx.add_timeout(delay_ms, callback)` - One-shot timer
