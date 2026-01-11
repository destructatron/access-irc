import access_irc.irc_manager as irc_manager


def _connection():
    config = {
        "name": "TestNet",
        "host": "irc.test",
        "channels": []
    }
    return irc_manager.IRCConnection(config, {})


def test_normalize_auto_commands():
    assert irc_manager.IRCConnection._normalize_auto_commands(None) == []
    assert irc_manager.IRCConnection._normalize_auto_commands("") == []

    commands = irc_manager.IRCConnection._normalize_auto_commands(
        " /raw WHOIS test \n\n /join #test \n  "
    )
    assert commands == ["/raw WHOIS test", "/join #test"]

    commands = irc_manager.IRCConnection._normalize_auto_commands(
        [" /away gone ", "", None, "/nick newnick"]
    )
    assert commands == ["/away gone", "/nick newnick"]


def test_calculate_max_message_length_accounts_for_overhead():
    connection = _connection()
    target = "#channel"
    extra_overhead = 9
    max_len = connection._calculate_max_message_length(target, extra_overhead)
    expected = (
        connection.IRC_MAX_LINE
        - (8 + len(target.encode("utf-8")) + 2 + 2 + connection.IRC_HOSTMASK_BUFFER + extra_overhead)
    )
    assert max_len == expected


def test_split_message_handles_utf8_boundaries():
    connection = _connection()
    message = "🔥" * 10
    chunks = connection._split_message(message, max_length=5)

    assert all(len(chunk.encode("utf-8")) <= 5 for chunk in chunks)
    assert "".join(chunks) == message
