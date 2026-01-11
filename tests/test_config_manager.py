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
