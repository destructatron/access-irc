#!/usr/bin/env bash
# Build Access IRC with the Python environment used by the application.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="$ROOT_DIR/venv/bin/python"

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    fail "venv Python not found at $PYTHON. Create the venv and install the application dependencies first."
fi

if [[ ! -f "$ROOT_DIR/access-irc.spec" || ! -f "$ROOT_DIR/launcher.py" ]]; then
    fail "PyInstaller spec or launcher is missing from $ROOT_DIR."
fi

if ! "$PYTHON" -c 'import PyInstaller' >/dev/null 2>&1; then
    fail "PyInstaller is not installed in the project venv. Run: venv/bin/python -m pip install -r requirements-build.txt"
fi

for output_dir in "$ROOT_DIR/build" "$ROOT_DIR/dist"; do
    if [[ -L "$output_dir" ]]; then
        fail "Refusing to use symlinked output directory: $output_dir"
    fi
done

printf 'Checking build dependencies using %s...\n' "$PYTHON"
if ! "$PYTHON" - <<'PY'
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

import miniirc
import pluggy
PY
then
    fail "A required application or GTK/GI dependency cannot be imported by the venv Python. Install the native dependencies from README.md, then run scripts/install_dependencies.py."
fi

if ! "$PYTHON" -c 'import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst; import gtkspellcheck, enchant' >/dev/null 2>&1; then
    printf 'Warning: GStreamer or spell-checking imports are unavailable; their optional features may not work in the bundle.\n' >&2
fi

PYINSTALLER_VERSION="$("$PYTHON" -c 'import PyInstaller; print(PyInstaller.__version__)')"
printf 'Building with PyInstaller %s...\n' "$PYINSTALLER_VERSION"

# Remove only this application's previous outputs, preserving unrelated files
# that may be stored in build/ or dist/.
rm -rf -- "$ROOT_DIR/build/access-irc" "$ROOT_DIR/dist/access-irc"

"$PYTHON" -m PyInstaller \
    --clean \
    --noconfirm \
    --workpath "$ROOT_DIR/build/access-irc" \
    --distpath "$ROOT_DIR/dist" \
    "$ROOT_DIR/access-irc.spec"

OUTPUT="$ROOT_DIR/dist/access-irc"
if [[ ! -f "$OUTPUT" || ! -x "$OUTPUT" || ! -s "$OUTPUT" ]]; then
    fail "PyInstaller completed without producing an executable at $OUTPUT."
fi

printf '\nBuild complete: %s\n' "$OUTPUT"
du -h -- "$OUTPUT"
cat <<'EOF'

The executable still requires compatible system GTK/GObject Introspection,
AT-SPI, GStreamer, and Enchant runtime libraries. Test it on the target
distribution before distributing it.
EOF
