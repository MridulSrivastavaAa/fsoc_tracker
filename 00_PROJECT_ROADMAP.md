# 00. PROJECT ROADMAP — ISRO FSOC PS 26169 Virtual Camera Tracking System

## Objective
Port the ISRO PS 26169 (SAC PS 26169) Virtual Camera Tracking System from a mock JS engine (local Web Worker +
local WebSockets) to a **real FastAPI backend** (`ClosedLoopEngine` over WebSocket `/ws/telemetry`), with a
**Three.js 3D web UI** (React 19 + @react-three/fiber + drei), and rebuild the standalone Windows `.exe`
(`FSOCTracker.exe`).

## Repository layout (repo root = `fsoc_tracker/`)
- `fsoc_tracker/fsoc_engine/` — Python FastAPI/OpenCV engine + server.
  - `src/fsoc/core/engine.py` (`ClosedLoopEngine`) — real backend.
  - `src/fsoc/server/app.py` — FastAPI app: `/ws/telemetry` (WebSocket), `/api/presets`, `/api/video/analyze`,
    static mounts (`/assets`, `/test_videos`, `/`).
  - `src/fsoc/core/config.py` — `AppConfig` (Pydantic), `default_config()`.
  - `src/fsoc/core/types.py` — `FullFrame`, `ViewportFrame`, `FrameMetrics`, `TrackState`, `CameraCommand`, `Detection`.
  - `src/fsoc/gui/app_3d.py` — native desktop 3D launcher (pywebview + edgechromium fallback).
  - `src/fsoc/gui/app.py` — Tkinter HUD.
  - `src/fsoc/control/`, `src/fsoc/tracking/`, `src/fsoc/vision/`, `src/fsoc/disturbances/`, `src/fsoc/simulation/`.
- `fsoc_tracker/web/` — TypeScript/React 3D frontend (Vite, React 19, @react-three/fiber + drei).
  - Source in `web/src/`; built output in `web/dist/` (produced by `npm run build`: `tsc -b && vite build`).
- `fsoc_tracker/fsoc_engine/build_exe.py` — root launcher that invokes the real PyInstaller spec
  (`fsoc_engine/build_exe.py`). PyInstaller packs `web/dist` → `web_dist` → `_internal/web_dist` inside the exe.
- `fsoc_tracker/web_dist/` — bundled web UI embedded in the exe (PyInstaller `datas`).
- `fsoc_tracker/configs/`, `fsoc_tracker/models/`, `fsoc_tracker/test_videos/` — defaults, ONNX models, benchmark frames.
- `fsoc_tracker/01_PROJECT_STRUCTURE.md`, `02_DESIGN_DOCUMENT.md`, `03_PDR_...`, `04_DATA_GENERATION_PLAN.md` — design/planning docs.

## Architecture
- **Web UI** (`web/src/services/providers.ts`): 3 providers —
  `LocalEngineProvider` (Web Worker), `RemoteEngineProvider` (WebSocket `ws://host/ws/telemetry`), `ReplayProvider`.
  Default server URL `http://localhost:8000` (env `VITE_NETRA_SERVER`).
- **Protocol** (`web/src/engine/protocol.ts`): command = start/pause/reset/config/replaceConfig/demo/mode/manual/
  reacquire/timeScale/imageRate; message = snapshot/frame/config/status/error.
- **Engine** (`web/src/core/engine.ts` `SimulationEngine`): pure TS closed-loop engine. Runs in the browser worker
  by default (the old "mock JS engine").
- **Python engine** (`fsoc_engine/src/fsoc/core/engine.py` `ClosedLoopEngine`): real backend. Feeds `/ws/telemetry`.
- **Server snapshot** (`fsoc_engine/src/fsoc/server/app.py` `build_snapshot`): emits `Snapshot` fields
  (`target`, `gimbal`, `camera`, `detection`, `kalman`, `error`, `control`, `disturbance`, `metrics`, `link`).
- **State machine**: `TrackingStateMachine` SEARCH→ACQUIRE→TRACK→LOST→REACQUIRE.

## Desired end state (user's acceptance criteria)
- Simulation, camera, 2D screen (2000²), and 3D simulation all run **smoothly** like the old exe.
- Satellite is **not inside Earth** — it sits at ~550 km altitude with correct FOV/conf.
- Camera, screen-2D, and 3D update live from the real FastAPI backend.
- Right-hand bar features (motion path, noise toggles, distortion, optics, tracking, experiment) visible and functional.
- Exe rebuilds cleanly with the new UI embedded.

## Key findings (root cause)
1. The exe embeds the **old legacy web build** (`_internal/web_dist/index.html` loads `assets/index-BBOzP7yQ.js`).
   The newer `web/dist` uses a different worker-relative asset mapping. Old embedded UI = stale/low-fidelity rendering.
2. **Snapshot schema mismatch**: the TS UI is written against the new backend schema, but the embedded old UI reads
   stale/possibly-missing fields (`error.px`/`estMagPx`, `kalman.estPx`, etc.). Field-name drift between backend and UI
   caused silent "no signal" / stuck renders.
3. Python and TS configs differ in shape (Python `AppConfig.yaml`/`config.py` with `res_x/res_y/fov_x/fov_y` +
   `px_per_deg_x/y`; TS `SimConfig` with `width/height/hfovDeg/vfovDeg` + `px_per_deg_x/fx`). Config drift drifts the
   FOV scale (4°×3° @ 640×480 = 160 px/deg) and hence the `screen_to_viewport`/`viewport_to_screen` mapping →
   satellite appears **inside Earth**.
4. Gauges/controls in `web/src/hud/` read `snapshot.gimbal.*` and `snapshot.error.*`; the old embedded UI and new UI
   disagreed on sign conventions (gimbal pan/tilt, `axisAz/axisEl`, `panCmd`/`tiltCmd`).

## Fixes that were applied
1. **Python `build_snapshot` schema** (`fsoc_engine/src/fsoc/server/app.py`):
   - `gimbal.tilt` / `boresightV`: emit **positive-up** elevation (negate Python's positive-down `tilt_deg`).
   - `gimbal.axisAz` / `axisEl`: emit *absolute* axis in world azimuth/elevation (no negation of `refEl`).
   - `gimbal.panCmd` / `tiltCmd`: emit the signed commanded rates (drop `abs()`), so the UI's PID/manual actions
     actually move the gimbal both directions.
   - `gimbal.goalU` / `goalV`: emit search goal in **viewport px** (degree→px), matching the TS `toPx()` used by
     `Sensor.tsx` / `Dock.tsx` / `VisBus.tsx`.
   - `gimbal.pan` / `tilt`: standardized azimuth/elevation (elevation positive-up) so the TS UI reads one consistent
     convention everywhere.
2. **Web UI rebuild** (`web/` `npm run build`), synced to `fsoc_engine/web_dist` (PyInstaller packaging source),
   and rebuilt the exe so `_internal/web_dist` serves the new UI.
3. **Exe repackaged** so the embedded UI matches the new build.

## Verification checklist
- `[ ]` `cd web && npm run build` → success (TypeScript + Vite).
- `[ ]` `fsoc_engine/build_exe.py` runs cleanly → `fsoc_engine/dist/FSOCTracker/FSOCTracker.exe` exists.
- `[ ]` `python -m fsoc.cli.main run --duration 3` → engine runs, acquisition ≤ 2 s, RMSE ≤ 10 px, fps ≥ 30.
- `[ ]` Start FastAPI; connect a WS client to `/ws/telemetry`; expect `snapshot` @ 30 Hz + `frame` at `imageRate` Hz,
  `status` every ~1 s. Confirm `state` transitions SEARCHING→DETECTED→ACQUIRING→TRACKING→LOCKED.
- `[ ]` Confirm sensor `DET` centroid moves toward FOV centre, pixel error drops, angular error drops.
- `[ ]` Confirm 3D satellite orbits at 550 km with correct FOV (~4°×3° window).
- `[ ]` Confirm right-hand bar: target/camera/link panels update live.
- `[ ]` Confirm exe launches and serves the rebuilt UI (`_internal/web_dist` asset hash).
