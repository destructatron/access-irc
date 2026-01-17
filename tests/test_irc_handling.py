import access_irc.irc_manager as irc_manager


class FakeIRC:
    def __init__(self, nick="IRCUser"):
        self.handlers = {}
        self.quoted = []
        self._desired_nick = nick
        self._current_nick = nick

    def Handler(self, event, colon=False):
        def decorator(func):
            self.handlers[event] = func
            return func
        return decorator

    def quote(self, command):
        self.quoted.append(command)


def _make_connection(overrides=None):
    config = {
        "name": "TestNet",
        "host": "irc.test",
        "channels": []
    }
    if overrides:
        config.update(overrides)
    return irc_manager.IRCConnection(config, {})


def test_strip_irc_formatting():
    text = "Hello \x02bold\x02 \x031,2red\x0F!"
    assert irc_manager.strip_irc_formatting(text) == "Hello bold red!"


def test_split_message_respects_limit():
    connection = _make_connection()
    message = "one two three four"
    chunks = connection._split_message(message, max_length=6)
    assert all(len(chunk.encode("utf-8")) <= 6 for chunk in chunks)
    assert "".join(chunks).replace(" ", "") == message.replace(" ", "")


def test_apply_mode_changes_updates_prefixes():
    connection = _make_connection()
    connection.channel_users["#chan"] = {"alice", "bob", "+carol"}

    changed = connection._apply_mode_changes("#chan", "+ov", ["alice", "bob"])
    assert changed is True

    users = connection.channel_users["#chan"]
    assert "@alice" in users
    assert "+bob" in users
    assert "+carol" in users
    assert "alice" not in users
    assert "bob" not in users

    changed = connection._apply_mode_changes("#chan", "-v", ["bob"])
    assert changed is True
    users = connection.channel_users["#chan"]
    assert "bob" in users
    assert "+bob" not in users


def test_topic_requested_on_self_join(monkeypatch):
    connection = _make_connection()
    fake = FakeIRC()
    connection.irc = fake
    connection.nickname = "me"

    monkeypatch.setattr(
        irc_manager.GLib,
        "idle_add",
        lambda func, *args, **kwargs: func(*args)
    )

    connection._register_handlers()
    join_handler = fake.handlers["JOIN"]
    join_handler(fake, ["me"], ["#test"])

    assert "#test" in connection.current_channels
    assert "TOPIC #test" in fake.quoted


def test_topic_requested_on_endofnames(monkeypatch):
    connection = _make_connection()
    fake = FakeIRC()
    connection.irc = fake
    connection.nickname = "me"

    monkeypatch.setattr(
        irc_manager.GLib,
        "idle_add",
        lambda func, *args, **kwargs: func(*args)
    )

    connection._register_handlers()
    end_handler = fake.handlers["366"]
    end_handler(fake, ["server"], ["me", "#bouncer", "End of /NAMES list"])

    assert "#bouncer" in connection.current_channels
    assert "TOPIC #bouncer" in fake.quoted


def test_alternate_nick_retry_on_in_use():
    connection = _make_connection({
        "nickname": "Primary",
        "alternate_nicks": ["AltOne", "AltTwo"]
    })
    fake = FakeIRC(connection.nickname)
    connection.irc = fake

    connection._handle_nick_error(
        "433",
        ["me", "Primary", "Nickname is already in use."]
    )

    assert connection.nickname == "AltOne"
    assert fake._desired_nick == "AltOne"
    assert fake._current_nick == "0AltOne"
    assert fake.quoted == ["NICK AltOne"]

    connection._handle_nick_error(
        "433",
        ["me", "AltOne", "Nickname is already in use."]
    )

    assert connection.nickname == "AltTwo"
    assert fake._desired_nick == "AltTwo"
    assert fake._current_nick == "0AltTwo"
    assert fake.quoted == ["NICK AltOne", "NICK AltTwo"]


def test_alternate_nick_not_used_when_connected():
    connection = _make_connection({
        "nickname": "Primary",
        "alternate_nicks": ["AltOne"]
    })
    fake = FakeIRC(connection.nickname)
    connection.irc = fake
    connection.connected = True

    connection._handle_nick_error(
        "433",
        ["me", "Primary", "Nickname is already in use."]
    )

    assert connection.nickname == "Primary"
    assert fake.quoted == []
