from datetime import datetime
from pathlib import Path

from access_irc.log_manager import LogManager


def test_log_write_creates_sanitized_paths(tmp_path):
    log_dir = tmp_path / "logs"
    manager = LogManager(str(log_dir))

    manager.log_message("Bad/../Server", "#chan", "alice", "hello")

    server_dirs = [p for p in log_dir.iterdir() if p.is_dir()]
    assert len(server_dirs) == 1

    server_dir = server_dirs[0]
    assert ".." not in server_dir.name
    assert "/" not in server_dir.name
    assert "\\" not in server_dir.name

    date_str = datetime.now().strftime("%Y-%m-%d")
    files = list(server_dir.iterdir())
    assert files, "Expected log file to be created"
    log_file = files[0]
    assert log_file.name.endswith(f"-{date_str}.log")

    contents = log_file.read_text(encoding="utf-8")
    assert "<alice> hello" in contents


def test_sanitize_name_handles_empty():
    manager = LogManager(None)
    assert manager._sanitize_name("") == "unnamed"
    assert manager._sanitize_name("...") == "unnamed"


def test_logging_disabled_no_file(tmp_path):
    log_dir = tmp_path / "logs"
    manager = LogManager(None)
    manager.log_message("Server", "#chan", "alice", "hello")
    assert not log_dir.exists()
