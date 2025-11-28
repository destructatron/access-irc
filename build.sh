#!/bin/bash
# Build script for Access IRC standalone executable

set -e

echo "Building Access IRC standalone executable..."

# Check if venv exists (we need it to get miniirc)
if [ ! -d "venv" ]; then
    echo "Error: venv directory not found"
    echo "Please create a venv and install dependencies first:"
    echo "  python3 -m venv venv"
    echo "  venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Copy miniirc from venv to project directory (temporary for build)
echo "Copying miniirc from venv..."
cp venv/lib/python3.13/site-packages/miniirc.py . || {
    echo "Error: Could not find miniirc in venv"
    echo "Install it with: venv/bin/pip install miniirc"
    exit 1
}

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist

# Build the executable using SYSTEM PyInstaller (not venv)
# This ensures we use system PyGObject which works with system GTK
echo "Running PyInstaller from system..."
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: PyInstaller not found in system"
    echo "Install it with: sudo apt install pyinstaller"
    echo "Or: pip3 install --user pyinstaller (and add ~/.local/bin to PATH)"
    exit 1
fi

/usr/bin/pyinstaller --clean access-irc.spec

# Clean up temporary miniirc copy
echo "Cleaning up..."
rm -f miniirc.py

echo ""
echo "Build complete!"
echo "Executable location: dist/access-irc"
echo "Executable size: $(du -h dist/access-irc | cut -f1)"
echo ""
echo "This executable bundles:"
echo "  ✓ Python interpreter"
echo "  ✓ miniirc library  "
echo "  ✓ Your access_irc code"
echo ""
echo "Users will need these system packages:"
echo "  - python3-gi (for PyGObject)"
echo "  - gir1.2-gtk-3.0 (for GTK 3)"
echo "  - at-spi2-core (for accessibility)"
echo "  - gstreamer1.0-plugins-base (for sounds)"
echo "  - gstreamer1.0-plugins-good (for sounds)"
echo ""
echo "Distribute: Just give users the dist/access-irc file!"
echo "They run it with: ./access-irc"
