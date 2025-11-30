# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Access IRC

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('access_irc/data/config.json.example', 'access_irc/data'),
    ],
    hiddenimports=[
        'gi',
        'gi.repository.Gtk',
        'gi.repository.Gdk',
        'gi.repository.GLib',
        'gi.repository.GObject',
        'gi.repository.Pango',
        'gi.repository.Gio',
        'gi.repository.Atk',
        'gi.repository.GdkPixbuf',
        'gi.repository.Gst',
        'gi.repository.Gspell',
        'miniirc',
        'access_irc',
        'access_irc.config_manager',
        'access_irc.sound_manager',
        'access_irc.irc_manager',
        'access_irc.log_manager',
        'access_irc.gui',
        'access_irc.server_dialog',
        'access_irc.preferences_dialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_gtk_custom.py'],
    excludes=[
        # Exclude optional test sound generation dependencies
        'numpy',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='access-irc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True if you want to see debug output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
