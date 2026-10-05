# -*- mode: python ; coding: utf-8 -*-
"""
NETRA.spec
==========
PyInstaller specification file for NETRA FSOC PAT Workstation.
Builds a frozen standalone distribution directory (onedir).

Usage:
    pyinstaller NETRA.spec --noconfirm --clean
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Ensure fsoc package is discoverable when running pyinstaller from fsoc_engine/
_src = Path(__file__).parent / 'src'
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Collect all fsoc modules dynamically
hidden = collect_submodules('fsoc') + [
    'PIL._tkinter_finder',
    'onnxruntime',
    'onnxruntime.capi',
    'pydantic',
    'pydantic_core',
    'uvicorn.loops.asyncio',
    'uvicorn.lifespan.off',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.protocols.http.h11_impl',
    'starlette.routing',
    'starlette.middleware',
    'starlette.staticfiles',
    'anyio._backends._asyncio',
    'anyio._backends._trio',
    'websockets.legacy',
    'websockets.legacy.server',
    'websockets.legacy.client',
    'multipart',
    'python_multipart',
]

# Bundled data directories
datas = [
    ('assets', 'assets'),
    ('models', 'models'),
    ('configs', 'configs'),
    ('web_dist', 'web_dist'),
]

# Platform-specific icon and version settings
icon_file = 'assets/netra.ico'
version_file = 'version_info.txt' if sys.platform == 'win32' else None

a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
        'tkinter.test',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# Optional Splash screen (PyInstaller splash feature is Windows-only)
splash = None
if sys.platform == 'win32':
    try:
        from PyInstaller.building.splash import Splash
        splash = Splash(
            'assets/splash.png',
            binaries=a.binaries,
            datas=a.datas,
            text_pos=(40, 325),
            text_size=11,
            text_color='#00e5ff',
            always_on_top=True,
        )
    except Exception:
        splash = None

exe_args = {
    'pyz': pyz,
    'scripts': a.scripts,
    'exclude_binaries': True,
    'name': 'NETRA',
    'debug': False,
    'bootloader_ignore_signals': False,
    'strip': False,
    'upx': False,
    'console': False,
    'disable_windowed_traceback': False,
    'target_arch': None,
    'codesign_identity': None,
    'entitlements_file': None,
}

if icon_file and Path(icon_file).exists():
    exe_args['icon'] = icon_file

if version_file and Path(version_file).exists():
    exe_args['version'] = version_file

if splash:
    exe = EXE(exe_args['pyz'], exe_args['scripts'], splash, [], **{k: v for k, v in exe_args.items() if k not in ('pyz', 'scripts')})
    coll_args = [exe, a.binaries, a.datas, splash.binaries]
else:
    exe = EXE(exe_args['pyz'], exe_args['scripts'], [], **{k: v for k, v in exe_args.items() if k not in ('pyz', 'scripts')})
    coll_args = [exe, a.binaries, a.datas]

coll = COLLECT(
    *coll_args,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NETRA',
)
