#!/usr/bin/env python3
"""
Launcher script for PyInstaller
This avoids relative import issues by importing the module properly
"""

import sys

# Import and run the main function
from access_irc.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
