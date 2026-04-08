# localdrop.spec  —  PyInstaller build spec for Windows
# Run from repo root: pyinstaller windows/localdrop.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['../localdrop.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('../assets/icon.ico', '.'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt5',
        'PyQt5.QtWidgets',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'qrcode',
        'qrcode.image.pil',
        'PIL',
        'PIL.Image',
        'http.server',
        'cgi',
        'email',
        'email.message',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='LocalDrop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # no console window — GUI only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/icon.ico',
    version='windows/version_info.txt',
)
