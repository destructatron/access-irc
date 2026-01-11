from access_irc.plugin_manager import PluginManager


def _write_plugin(path, content):
    path.write_text(content, encoding="utf-8")


def test_plugin_discovery_and_hooks(tmp_path):
    filter_plugin = tmp_path / "filter_plugin.py"
    setup_plugin = tmp_path / "setup_plugin.py"
    bad_plugin = tmp_path / "bad_plugin.py"

    _write_plugin(
        filter_plugin,
        "\n".join([
            "from access_irc.plugin_specs import hookimpl",
            "",
            "class Plugin:",
            "    @hookimpl",
            "    def filter_incoming_message(self, ctx, server, target, sender, message):",
            "        return {'message': message + '!'}",
            "",
            "    @hookimpl",
            "    def on_command(self, ctx, server, target, command, args):",
            "        if command == 'ping':",
            "            return True",
        ])
    )

    _write_plugin(
        setup_plugin,
        "\n".join([
            "from access_irc.plugin_specs import hookimpl",
            "",
            "seen = {}",
            "",
            "class _Plugin:",
            "    @hookimpl",
            "    def on_message(self, ctx, server, target, sender, message, is_mention):",
            "        seen['last'] = (server, target, sender, message, is_mention)",
            "",
            "def setup(ctx):",
            "    return _Plugin()",
        ])
    )

    _write_plugin(
        bad_plugin,
        "\n".join([
            "from access_irc.plugin_specs import hookimpl",
            "",
            "class Plugin:",
            "    @hookimpl",
            "    def on_message(self, ctx, server, target, sender, message, is_mention):",
            "        raise RuntimeError('boom')",
        ])
    )

    manager = PluginManager()
    manager.plugins_dir = tmp_path

    loaded = manager.discover_and_load_plugins()
    assert loaded == 3

    result = manager.filter_incoming_message("srv", "#chan", "alice", "hi")
    assert result == {"message": "hi!"}

    assert manager.call_command("srv", "#chan", "ping", "") is True

    # Ensure on_message works and does not raise on plugin errors
    manager.call_message("srv", "#chan", "alice", "hello", False)

    seen = manager.loaded_plugins["setup_plugin"]["module"].seen
    assert seen["last"] == ("srv", "#chan", "alice", "hello", False)
