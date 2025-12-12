#!/usr/bin/env python3
"""Setup script for Access IRC"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="access-irc",
    version="1.6.0",
    description="An accessible IRC client for Linux with screen reader support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Access IRC Contributors",
    url="https://github.com/destructatron/access-irc",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "access_irc": [
            "data/config.json.example",
            "data/sounds/*.wav",
        ],
    },
    python_requires=">=3.7",
    install_requires=[
        "miniirc>=1.9.0",
        "PyGObject>=3.40.0",
    ],
    extras_require={
        "soundgen": [
            "numpy>=1.20.0",
            "scipy>=1.7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "access-irc=access_irc.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: GTK",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Communications :: Chat :: Internet Relay Chat",
        "Topic :: Desktop Environment :: Gnome",
    ],
    keywords="irc accessibility screen-reader gtk at-spi2 chat",
)
