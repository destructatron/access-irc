"""Tests for AT-SPI2 announcement channel context in AccessIRCApplication.

Verifies that on_irc_join, on_irc_part, on_irc_quit, and on_irc_nick pass
(server, channel) context to should_announce_all_messages(), so per-channel
announcement overrides (F2 toggle) are respected.
"""

from unittest.mock import MagicMock, call

from access_irc.__main__ import AccessIRCApplication


class FakeConnection:
    """Minimal IRCConnection stand-in with nickname and channel_users."""

    def __init__(self, nickname="TestUser", channel_users=None):
        self.nickname = nickname
        self.channel_users = channel_users or {}


def _make_app():
    """Create an AccessIRCApplication without calling __init__ (avoids GTK).

    All manager dependencies are replaced with MagicMock objects so event
    handler methods can be called directly in tests.
    """
    app = object.__new__(AccessIRCApplication)

    app.window = MagicMock()
    app.window.current_server = None
    app.window.current_target = None
    app.window.should_announce_all_messages = MagicMock(return_value=False)
    app.window.announce_to_screen_reader = MagicMock()

    app.irc = MagicMock()
    app.irc.connections = {}

    app.config = MagicMock()
    app.config.get_nickname.return_value = "TestUser"
    # Empty log directory makes _should_log_server() return False immediately.
    app.config.get_log_directory.return_value = ""

    app.log = MagicMock()
    app.plugins = MagicMock()
    app.sound = MagicMock()

    return app


# -- Join announcements -------------------------------------------------------


def test_join_announces_with_channel_context():
    app = _make_app()
    app.window.should_announce_all_messages.return_value = True

    app.on_irc_join("MyServer", "#python", "alice")

    app.window.should_announce_all_messages.assert_called_once_with("MyServer", "#python")
    app.window.announce_to_screen_reader.assert_called_once_with("alice has joined #python")


def test_join_no_announce_when_channel_disabled():
    app = _make_app()
    app.window.should_announce_all_messages.return_value = False

    app.on_irc_join("MyServer", "#python", "alice")

    app.window.should_announce_all_messages.assert_called_once_with("MyServer", "#python")
    app.window.announce_to_screen_reader.assert_not_called()


# -- Part announcements -------------------------------------------------------


def test_part_announces_with_channel_context():
    app = _make_app()
    app.window.should_announce_all_messages.return_value = True

    app.on_irc_part("MyServer", "#python", "alice", "goodbye")

    app.window.should_announce_all_messages.assert_called_once_with("MyServer", "#python")
    app.window.announce_to_screen_reader.assert_called_once_with(
        "alice has left #python (goodbye)"
    )


def test_part_no_announce_when_channel_disabled():
    app = _make_app()
    app.window.should_announce_all_messages.return_value = False

    app.on_irc_part("MyServer", "#python", "alice", "")

    app.window.should_announce_all_messages.assert_called_once_with("MyServer", "#python")
    app.window.announce_to_screen_reader.assert_not_called()


# -- Quit announcements -------------------------------------------------------


def test_quit_checks_each_affected_channel():
    app = _make_app()
    channels = ["#python", "#rust", "#go"]

    # Only #rust has announcements enabled.
    def side_effect(server, ch):
        return ch == "#rust"

    app.window.should_announce_all_messages.side_effect = side_effect

    app.on_irc_quit("MyServer", "alice", "Ping timeout", channels)

    # any() short-circuits, so #python (False) and #rust (True) are checked;
    # #go may or may not be checked.  Verify the ones we know about.
    calls = app.window.should_announce_all_messages.call_args_list
    assert call("MyServer", "#python") in calls
    assert call("MyServer", "#rust") in calls
    app.window.announce_to_screen_reader.assert_called_once_with(
        "alice has quit (Ping timeout)"
    )


def test_quit_no_announce_when_all_channels_disabled():
    app = _make_app()
    channels = ["#python", "#rust"]
    app.window.should_announce_all_messages.return_value = False

    app.on_irc_quit("MyServer", "alice", "Quit", channels)

    assert app.window.should_announce_all_messages.call_count == 2
    app.window.announce_to_screen_reader.assert_not_called()


def test_quit_announces_once_even_if_multiple_channels_enabled():
    app = _make_app()
    channels = ["#python", "#rust"]
    app.window.should_announce_all_messages.return_value = True

    app.on_irc_quit("MyServer", "alice", "Quit", channels)

    # any() short-circuits after the first True, so only 1 call.
    app.window.announce_to_screen_reader.assert_called_once()


# -- Nick change announcements ------------------------------------------------


def test_nick_checks_only_affected_channels():
    app = _make_app()
    conn = FakeConnection(
        nickname="me",
        channel_users={
            "#python": {"bob_new", "me"},
            "#rust": {"bob_new", "carol"},
            "#go": {"dave"},  # bob_new is NOT in this channel
        },
    )
    app.irc.connections = {"MyServer": conn}

    # Return False so any() doesn't short-circuit and all channels are checked.
    app.window.should_announce_all_messages.return_value = False

    app.on_irc_nick("MyServer", "bob", "bob_new")

    checked_channels = {
        c.args[1] for c in app.window.should_announce_all_messages.call_args_list
    }
    # Only channels where bob_new is present should be checked.
    assert "#python" in checked_channels
    assert "#rust" in checked_channels
    assert "#go" not in checked_channels
    # All returned False, so no announcement.
    app.window.announce_to_screen_reader.assert_not_called()


def test_nick_announces_when_any_channel_enabled():
    app = _make_app()
    conn = FakeConnection(
        nickname="me",
        channel_users={
            "#python": {"bob_new", "me"},
            "#rust": {"bob_new", "carol"},
        },
    )
    app.irc.connections = {"MyServer": conn}
    app.window.should_announce_all_messages.return_value = True

    app.on_irc_nick("MyServer", "bob", "bob_new")

    app.window.announce_to_screen_reader.assert_called_once_with(
        "bob is now known as bob_new"
    )


def test_nick_no_announce_when_all_channels_disabled():
    app = _make_app()
    conn = FakeConnection(
        nickname="me",
        channel_users={
            "#python": {"bob_new", "me"},
            "#rust": {"bob_new"},
        },
    )
    app.irc.connections = {"MyServer": conn}
    app.window.should_announce_all_messages.return_value = False

    app.on_irc_nick("MyServer", "bob", "bob_new")

    assert app.window.should_announce_all_messages.call_count == 2
    app.window.announce_to_screen_reader.assert_not_called()


def test_own_nick_change_announces_directly():
    """Own nick change is always announced directly without checking channel overrides."""
    app = _make_app()
    conn = FakeConnection(
        nickname="new_me",  # IRCManager already updated this
        channel_users={"#python": {"new_me"}},
    )
    app.irc.connections = {"MyServer": conn}

    app.on_irc_nick("MyServer", "old_me", "new_me")

    # Own nick change is announced unconditionally.
    app.window.announce_to_screen_reader.assert_any_call(
        "Your nickname has been changed from old_me to new_me"
    )
    # should_announce_all_messages should NOT be called (is_own_nick skips it).
    app.window.should_announce_all_messages.assert_not_called()
