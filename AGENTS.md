# Repository Guidelines

## Project Structure & Module Organization
- `access_irc/` is the main Python package (GTK UI, managers, IRC logic). Key entry points: `access_irc/__main__.py` and `access_irc/gui.py`.
- `access_irc/data/` contains bundled assets such as `config.json.example` and default sounds.
- `scripts/` hosts developer utilities like sound generation.
- `examples/` provides sample configs or usage artifacts.
- Packaging artifacts live at the repo root (`setup.py`, `requirements.txt`, `access-irc.spec`, `build.sh`).

## Build, Test, and Development Commands
- `python3 -m venv venv && source venv/bin/activate` creates an isolated dev env.
- `pip install -e .` installs in editable mode for local development.
- `python3 -m access_irc` runs the app as a module; `access-irc` runs the console entry point.
- `python3 scripts/generate_sounds.py` regenerates default sound assets (requires `numpy`/`scipy`).
- `./build.sh` builds the standalone binary using system PyInstaller.

## Coding Style & Naming Conventions
- Python style follows PEP 8: 4-space indentation, `snake_case` for functions/vars, `CapWords` for classes.
- Keep GTK calls on the main thread; use `GLib.idle_add()` for UI updates from IRC threads.
- Prefer small, focused manager methods; see `access_irc/*_manager.py` for patterns.

## Testing Guidelines
- No automated test suite is currently present. Do manual smoke checks:
  - Launch the app, connect to a test IRC server, send/receive a message, and verify screen reader announcements and sounds.
 - Pytest-based unit tests live in `tests/`. Run them with:
   - `venv/bin/python -m pytest`

## Commit & Pull Request Guidelines
- Commit messages in history are short, imperative, and sentence case (e.g., “Add DCC support”).
- PRs should include a concise summary, test notes (manual steps if applicable), and screenshots for UI changes.

## Agent-Specific Notes
- See `CLAUDE.md` for architecture details and critical threading constraints.
