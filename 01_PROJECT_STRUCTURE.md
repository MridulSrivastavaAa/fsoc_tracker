# 01. PROJECT STRUCTURE

## Root layout
- `fsoc_tracker/_internal/` — PyInstaller bundle embedded in `FSOCTracker.exe`
  - `src/fsoc/...` — Python engine + server (same code as `fsoc_engine/`)
  - `web_dist/` — bundled web UI (index.html + assets/)
  - `configs/`, `models/`, `test_videos/`, native DLLs, `.py` interpreters
- `fsoc_tracker/FSOCTracker.exe` — the compiled desktop app
- `fsoc_tracker/web/` — TypeScript/React 3D frontend source + build
  - `package.json`, `vite.config.ts`
  - `src/` — React 19 + @react-three/fiber + drei + zustand + three 0.186
  - `dist/` — built output (copied to `fsoc_engine/web_dist/` by `build_exe.py`)
- `fsoc_tracker/fsoc_engine/` — Python FastAPI/OpenCV engine + server
  - `src/fsoc/core/engine.py` — `ClosedLoopEngine` (the REAL backend)
  - `src/fsoc/server/app.py` — FastAPI app: `/ws/telemetry` (WebSocket), `/api/presets`, `/api/video/analyze`, static mounts
  - `src/fsoc/core/config.py` — `AppConfig` (Pydantic), `default_config()`
  - `src/fsoc/core/types.py` — `FullFrame`, `ViewportFrame`, `FrameMetrics`, `TrackState`, `CameraCommand`, `Detection`
  - `src/fsoc/gui/app_3d.py` — native desktop 3D launcher (pywebview + edgechromium fallback)
  - `src/fsoc/gui/app.py` — Tkinter HUD
  - `src/fsoc/control/`, `src/fsoc/tracking/`, `src/fsoc/vision/`, `src/fsoc/disturbances/`, `src/fsoc/simulation/`
- `fsoc_tracker/models/` — ONNX models (`beacon_verifier.onnx`, `test_verifier.onnx`)
- `fsoc_tracker/configs/` — default YAML
- `fsoc_tracker/test_videos/` — benchmark frames
- `fsoc_tracker/build_exe.py` — PyInstaller spec + build script
- `fsoc_tracker/FSOCTracker.spec`, `fsoc_tracker/run_benchmarks.bat`, `run_demo.bat`

## Key file-to-artifact mapping
- Exe embeds: `_internal/web_dist/` (older build) -> `web_dist/index.html` + `assets/`
- New build: `web/dist/` -> copied to `fsoc_engine/web_dist/` -> `_internal/web_dist/` (packaged)
- `fsoc_engine/build_exe.py` copies `web/dist` -> `fsoc_engine/web_dist` before PyInstaller.
