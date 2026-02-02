from access_irc.config_manager import ConfigManager


def test_config_creation_and_persistence(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(str(config_path))

    assert config_path.exists()
    assert manager.get_nickname()

    manager.set_nickname("Tester")
    reloaded = ConfigManager(str(config_path))
    assert reloaded.get_nickname() == "Tester"


def test_merge_with_defaults_adds_missing_keys(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(str(config_path))

    merged = manager._merge_with_defaults({
        "nickname": "CustomNick",
        "sounds": {"enabled": False}
    })

    assert merged["nickname"] == "CustomNick"
    assert "dcc" in merged
    assert merged["sounds"]["enabled"] is False
    assert "message" in merged["sounds"]


def test_server_add_update_remove(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(str(config_path))

    server = {
        "name": "TestNet",
        "host": "irc.test",
        "port": 6667,
        "ssl": False,
        "channels": ["#test"]
    }
    initial_count = len(manager.get_servers())
    manager.add_server(server)
    assert len(manager.get_servers()) == initial_count + 1

    updated = dict(server)
    updated["host"] = "irc.example"
    index = len(manager.get_servers()) - 1
    assert manager.update_server(index, updated) is True
    assert manager.get_servers()[index]["host"] == "irc.example"

    assert manager.remove_server(index) is True
    assert len(manager.get_servers()) == initial_count


def test_alternate_nicks_roundtrip(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(str(config_path))

    manager.set_alternate_nicks(["AltOne", "AltTwo", " ", "AltOne"])
    reloaded = ConfigManager(str(config_path))

    assert reloaded.get_alternate_nicks() == ["AltOne", "AltTwo"]


def test_add_ignored_nick(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    assert manager.add_ignored_nick("TestNet", "Spammer") is True
    assert manager.add_ignored_nick("TestNet", "spammer") is False  # duplicate (case-insensitive)
    assert manager.get_ignored_nicks("TestNet") == ["spammer"]


def test_remove_ignored_nick(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    manager.add_ignored_nick("TestNet", "Spammer")
    assert manager.remove_ignored_nick("TestNet", "SPAMMER") is True  # case-insensitive
    assert manager.get_ignored_nicks("TestNet") == []
    assert manager.remove_ignored_nick("TestNet", "Spammer") is False  # not found


def test_is_nick_ignored(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    manager.add_ignored_nick("TestNet", "Troll")
    assert manager.is_nick_ignored("TestNet", "troll") is True
    assert manager.is_nick_ignored("TestNet", "TROLL") is True
    assert manager.is_nick_ignored("TestNet", "other") is False
    assert manager.is_nick_ignored("OtherNet", "troll") is False


def test_get_ignored_nicks_unknown_server(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    assert manager.get_ignored_nicks("NoSuchServer") == []


def test_ignored_nicks_persistence(tmp_path):
    config_path = tmp_path / "config.json"
    manager = ConfigManager(str(config_path))

    manager.add_ignored_nick("TestNet", "Spammer")
    manager.add_ignored_nick("TestNet", "Troll")
    manager.add_ignored_nick("OtherNet", "Bot")

    reloaded = ConfigManager(str(config_path))
    assert sorted(reloaded.get_ignored_nicks("TestNet")) == ["spammer", "troll"]
    assert reloaded.get_ignored_nicks("OtherNet") == ["bot"]


def test_ignored_nicks_migrate_on_server_rename(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    server = {"name": "OldName", "host": "irc.test", "port": 6667,
              "ssl": False, "channels": []}
    manager.add_server(server)
    manager.add_ignored_nick("OldName", "spammer")
    manager.add_ignored_nick("OldName", "troll")

    renamed = dict(server)
    renamed["name"] = "NewName"
    index = len(manager.get_servers()) - 1
    manager.update_server(index, renamed)

    # Old key gone, new key has the list
    assert manager.get_ignored_nicks("OldName") == []
    assert sorted(manager.get_ignored_nicks("NewName")) == ["spammer", "troll"]


def test_ignored_nicks_no_migrate_when_name_unchanged(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"))

    server = {"name": "TestNet", "host": "irc.test", "port": 6667,
              "ssl": False, "channels": []}
    manager.add_server(server)
    manager.add_ignored_nick("TestNet", "spammer")

    updated = dict(server)
    updated["host"] = "irc.example"
    index = len(manager.get_servers()) - 1
    manager.update_server(index, updated)

    assert manager.get_ignored_nicks("TestNet") == ["spammer"]
