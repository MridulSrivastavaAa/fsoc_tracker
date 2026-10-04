# 02. DESIGN DOCUMENT — ISRO FSOC PS 26169

## System block diagram
```
  [Web UI (React 3D)] <-WebSocket-> [FastAPI server :8000]
         |  WS /ws/telemetry            |  (build_snapshot)
         v                                v
  [Local Worker engine (old)]    [Real engine: ClosedLoopEngine]
  (browser TS)                     (Python, OpenCV + numpy + onnx)
```

## Message protocol (frontend `engine/protocol.ts`)
- **Command** (client → server): `start`, `pause`, `reset`, `config` (patch), `replaceConfig`, `demo`, `mode`, `manual`, `reacquire`, `timeScale`, `imageRate`.
- **Message** (server → client): `snapshot` (telemetry JSON), `frame` (AQF1 binary image), `config` (engine state), `status` (running/demo/fps/timeScale), `error`.

## Snapshot schema (TS `core/telemetry/types.ts` = source of truth)
`Snapshot` = { t, frame, state: TrackState, stateSince, mode, running, source, target, gimbal, camera, detection, candidates, procMs, roi, kalman, error, control, disturbance, metrics, link, timeline, events, demo, plan? }

Key sub-objects:
- `target`: { az, el, rangeKm, posKm, u, v, angRateDegS, transverseKmS, inFov, truthPx, decoyPx, refAz, refEl }
- `gimbal`: { pan, tilt, panRate, tiltRate, panCmd, tiltCmd, atLimit, axisAz, axisEl, boresightU, boresightV, goalU, goalV }
- `camera`: { width, height, hfovDeg, vfovDeg, ifovDeg, focalMm, fx }
- `error`: { px, magPx, angDeg, estMagPx }
- `metrics`: { elapsedS, frames, tDetect, tTrack, acquisitionS, errMeanPx, errRmsPx, errMaxPx, errP95Px, centroidRmsPx, falseDetections, lossPct, lossEvents, reacqMeanS, reacqMaxS, lockRetentionPct, procMeanMs, procMaxMs, fps, aqs, acceptance }
- `link`: { rangeKm, geomLossDb, atmLossDb, pointingLossDb, prDbm, marginDb, fineHandover, pAcquire2s, pInitialInView, pDetectFrame }

## Python config shape (`AppConfig`, `config.py`)
- `camera`: res_x, res_y, fov_x_deg, fov_y_deg, px_per_deg_x (= res_x/fov_x), px_per_deg_y (= res_y/fov_y), half_w, half_h, ...
- `target`: trajectory, speedDegS, amplitudeDeg, periodS, headingDeg, startMode, startUDeg, startVDeg, waypoints, spotSizePx, spotShape, beaconIntensity, rangeKm
- `gimbal`: maxRateDegS, maxAccelDegS2, rateLagS, panMinDeg, panMaxDeg, tiltMinDeg, tiltMaxDeg
- `disturbance`: vibrationPx, vibrationHz, jitterPx, platformMotion, platformMotionPx, windDegS, targetNoiseDeg, gaussianNoise, saltPepper, poisson, atmosphere, atmosphereStrength, turbulence, dropoutProb, occlusionPeriodS, occlusionDurS, decoy
- `tracking.tracker_type`: "kalman" | "imm"

## TS config shape (`SimConfig`, `config.ts`)
- `camera`: width, height, hfovDeg, wideAcquisition, wideHfovDeg, zoomRateDegS, frameRateHz, pixelPitchUm
- `logic`: lockPx, unlockPx, lockFrames, acquirePx, confirmM, confirmN, coastFrames, lostHoldS, reacquireTimeoutS, searchHalfUDeg, searchHalfVDeg

## Camera / FOV mapping (the tip of the iceberg)
- PS reference: 4° × 3° at 640×480 → **px_per_deg_x = 160, px_per_deg_y = 160**.
- `screen → viewport` and `viewport → screen` conversions use those scales. Any drift (incorrect `fov_x`/`fov_y`, wrong `res_x`/`res_y`, or stale embedded UI using old constants) makes the 3D camera think the satellite is at the Earth's centre → satellite "inside Earth" at height 0.

## 3D camera (`scene/CameraRig.tsx`)
- `overview`, `terminal`, `link`, `follow`, `orbit`, `sensor`, `free` presets.
- `Sensor` POV places the 3D camera at the terminal lens using `vis.axisAz/axisEl` and the terminal camera's `vfov`.
- `useFrame` priority: `-1.5` for the spacecraft chase camera; `-1` for `sensor` POV; the pipeline renders after `CameraControls`.

## Performance budget
- Pipeline target ≥ 30 FPS; per-frame budget ≤ ~15 ms (server reports `procMeanMs` ~4–8 ms, `fps` 30).
- Engine frame rate: `imageRate` default 15 Hz (configurable 2–60). `quality` low/medium/high maps to `imageRate` 8/15/30.
