#!/usr/bin/env python3
"""Install Access IRC and choose a PyGObject version for the host GI API."""

import argparse
import shutil
import subprocess
import sys


def pkg_config_has(package):
    if not shutil.which("pkg-config"):
        return False
    return subprocess.run(
        ["pkg-config", "--exists", package], check=False
    ).returncode == 0


def run(*command):
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel",
        action="store_true",
        help="install the project normally instead of in editable mode",
    )
    args = parser.parse_args()

    if pkg_config_has("girepository-2.0"):
        pygobject_requirement = "PyGObject>=3.52.0"
    elif pkg_config_has("gobject-introspection-1.0"):
        pygobject_requirement = "PyGObject>=3.40.0,<3.52"
    else:
        parser.error(
            "GObject Introspection development files were not found. Install "
            "the package for your distribution (for Debian Bookworm: "
            "libgirepository1.0-dev), then retry."
        )

    run(sys.executable, "-m", "pip", "install", pygobject_requirement)
    # Install PyGObject first: pygtkspellcheck depends on it, but does not
    # constrain it to the GI API supported by the host.
    run(sys.executable, "-m", "pip", "install", "-r", "requirements.txt")
    install_command = [sys.executable, "-m", "pip", "install"]
    if not args.wheel:
        install_command.append("-e")
    install_command.append(".")
    run(*install_command)


if __name__ == "__main__":
    main()
