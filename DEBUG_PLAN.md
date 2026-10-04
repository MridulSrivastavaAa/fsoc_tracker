# DEBUG PLAN — Root-cause & Verification Checklist

## Symptom → root-cause mapping
| Symptom | Likely cause | Confirm |
|---|---|---|
| Satellite inside Earth (height 0) | FOV/px-per-degree mismatch; old embedded UI | Compare `camera.fov_x/y_deg`, `fx`, `px_per_deg_x` between TS config and backend snapshot |
| Screen 2D (2000²) stuck/slow | `imageRate` 15 Hz; binary frame decode; stale old UI | Check `providerStatus` / `engineFps` / `latestFrame` in store; Firefox/F12 Network tab |
| 3D camera weird paths / diamonds | Gimbal sign or `axisAz/axisEl` drift; `sensor` POV `basisFromAzEl` | Print `gimbal.axisAz/axisEl`, `camera.fov`, `screen space` in TS |
| Right-hand-bar (motion path/noise/optics) not working | Old embedded UI layout + stale refs | Rebuild UI; check `hud` snapshot fields arrive |
| Camera/3D not updating | Backend not streaming or field-name typo | Inspect WS messages in F12 Network |

## Verification steps (run after each change)
1. `cd web && npm run build` → must succeed.
2. `cp -rf web/dist/* fsoc_engine/web_dist/` (sync).
3. Start FastAPI: `cd fsoc_engine && python -m fsoc.server.app` (or `python main.py`).
4. `npm run dev` (Vite) with proxy `/api → http://127.0.0.1:8000` — or serve bundled UI directly.
5. Open `http://localhost:5173/`, F12 → Network → watch `/ws/telemetry`.
   - Expect: `snapshot` every frame (30 Hz), `frame` at `imageRate` Hz (15–30 Hz), `status` every ~1 s.
6. Confirm `snapshot.state` transitions SEARCHING → DETECTED → ACQUIRING → TRACKING → LOCKED.
7. Confirm sensor `DET` centroid moves toward FOV centre, pixel error drops, angular err drops.
8. Confirm 3D satellite orbits at 550 km with correct FOV (~4°×3° window).
9. Confirm right-hand bar: target/camera/link panels update live.
10. Confirm exe launches and serves the rebuilt UI (check `_internal/web_dist` asset hash).

## Logs
- `/fsoc_tracker/fsoc_engine/browser_errors.log` — client-side errors.
- FastAPI stdout — simulation-loop errors (printed in `app.py`).
- Exe console (`--console` or error dialog) — PyInstaller stderr.
