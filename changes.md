# CHANGES — ISRO FSOC PS 26169

## v1.0 (current)
- Real FastAPI backend + Three.js 3D web UI + standalone exe.

## Known issues (before fix)
- EXE serves OLD embedded web build (stale `assets/index-BBOzP7yQ.js`), so new features are missing/malformed.
- Snapshot schema mismatch between new backend and UI → silent no-signal / stuck renders.
- Gimbal sign/FOV drift → satellite appears inside Earth.
- 2D screen (2000²) and right-hand-bar features not wiring correctly.

## Fixes to apply
1. Sync `web/dist` → `fsoc_engine/web_dist` → `_internal/web_dist` (PyInstaller packaged).
2. Reconcile TS ↔ Python snapshot schema (source of truth = TS `types.ts`).
3. Fix FOV/px-per-degree mapping so the satellite is at 550 km, not Earth centre.
4. Fix gimbal sign convention (`axisAz/axisEl`, `pan`/`tilt`) for 2D/3D consistency.
5. Rebuild exe and verify.
