# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/launcher.py'],
    pathex=['C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/src'],
    binaries=[],
    datas=[('C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/configs', 'configs'), ('C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/models', 'models'), ('C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/web_dist', 'web_dist'), ('C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/src', 'src'), ('C:/Users/mridu/OneDrive/Desktop/new project/fsoc_engine/test_videos', 'test_videos')],
    hiddenimports=['webview', 'bottle', 'pythonnet', 'clr', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'fastapi.middleware.cors', 'fastapi.staticfiles', 'starlette', 'starlette.routing', 'starlette.middleware.cors', 'starlette.staticfiles', 'multipart', 'multipart.multipart', 'pydantic', 'websockets'],
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
