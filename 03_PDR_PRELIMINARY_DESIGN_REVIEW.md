# 03. PDR — PRELIMINARY DESIGN REVIEW

## Integration contract between TS UI and Python backend
1. **Snapshot field names** must match `web/src/core/telemetry/types.ts` exactly. The TS UI reads `snapshot.gimbal.x`, `snapshot.error.x`, `snapshot.kalman.x`, `snapshot.metrics.x`. Any rename/drop in the backend silently kills features.
2. **Config shape** must be compatible: UI sends `replaceConfig` with TS `SimConfig` shape → server must `model_validate` into `AppConfig`. Currently `AppConfig.model_validate` expects Python YAML/Pydantic shape. Need a TS↔Python adapter or shared JSON contract.
3. **Gimbal sign convention**: backend `build_snapshot` renders `gimbal.tilt` as `-tilt` (inverts Y for "elevation" UI); TS UI must be consistent or the 3D `axisAz/axisEl` and 2D overlays draw mirrored.
4. **FOV scale**: backend `camera.fov_x_deg`/`fov_y_deg` + `px_per_deg_x/y` drive the 2D screen-2000² and the sensor overlay; TS `camera.width/height/hfovDeg/vfovDeg/ifovDeg` must derive the same values.
5. **Frame rate**: `imageRate` 15 Hz default means the binary camera **frames** arrive at 15 Hz even though snapshots stream at 30 Hz. UI should not assume `frame` === `snapshot.frame`.
