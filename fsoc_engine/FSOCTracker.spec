# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/SIH/final_2/fsoc_tracker/fsoc_engine/launcher.py'],
    pathex=['C:/SIH/final_2/fsoc_tracker/fsoc_engine/src'],
    binaries=[],
    datas=[('C:/SIH/final_2/fsoc_tracker/fsoc_engine/configs', 'configs'), ('C:/SIH/final_2/fsoc_tracker/fsoc_engine/models', 'models'), ('C:/SIH/final_2/fsoc_tracker/fsoc_engine/web_dist', 'web_dist'), ('C:/SIH/final_2/fsoc_tracker/fsoc_engine/src', 'src'), ('C:/SIH/final_2/fsoc_tracker/fsoc_engine/test_videos', 'test_videos')],
    hiddenimports=['webview', 'bottle', 'pythonnet', 'clr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FSOCTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FSOCTracker',
)
