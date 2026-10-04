# NETRA Algorithm Plugin Playground: Discovery Summary

## 1. Engine calls

- **Detector**: `engine.py`, lines 133, 180 (`self.detector.detect`)
- **CNN Verifier**: `engine.py`, lines 134, 181 (`self.verifier.verify_detections`)
- **Optical Flow**: `engine.py`, lines 140, 188 (`self.optical_flow.estimate_flow`)
- **IMM Tracker (and Kalman)**: `engine.py`, lines 137 (`init_track`), 176 (`predict`), 221 (`update`), 227 (`coast`), 280 (`get_state`)
- **Particle Filter (PF)**: `engine.py`, lines 201 (`predict`), 204 (`update`), 215/225 (`reset`), 239 (`initialize`)
- **State Machine**: `engine.py`, lines 148, 172, 222, 228 (`step`)
- **PID Controller**: `engine.py`, lines 255, 258, 261 (`self.controller.compute`)
- **Turbulence Compensator**: `engine.py`, line 267 (`self.turbulence_comp.process_frame`)
- **Calibration**: Currently there is no calibration call between vision and tracking in the default engine. (Phase 8 will introduce this).

## 2. Classes, constructors, per-frame methods, input/output types

- `SpotDetector(cfg, preprocessor)`: `detect(img, mask, intensity_image)` -> list of candidate objects
- `BeaconVerifierCNN(cfg)`: `verify_detections(img, candidates)` -> filtered candidates
- `OpticalFlowTracker(cfg.vision.optical_flow, dt)`: `estimate_flow(...)` -> flow dict/object
- `IMMTracker(cfg, dt)` / `KalmanTracker(cfg, dt)`: `predict()`, `update()`, `coast()`, `get_state()` -> `TrackState` dataclass
- `ParticleFilter(cfg, dt, viewport_w, viewport_h, seed)`: `predict()`, `update(candidates)` -> `pf_state`
- `PIDController(cfg, camera_cfg, dt)`: `compute(x, y, vx, vy, state)` -> `CameraCommand` dataclass (pan_rate_deg_per_s, tilt_rate_deg_per_s)

*Most components use Python dataclasses or objects for outputs (`TrackState`, `CameraCommand`), and ndarray for images.*

## 3. Tracking error vs ground truth

Tracking error is computed in `engine.py` (lines 305/318) as the Euclidean pixel distance between the Kalman estimated position and the ground truth viewport position:
`error_px = float(np.hypot(track_state.x - gt_vp.x, track_state.y - gt_vp.y))`
Boresight error (R14) is distance from optical axis: `boresight_px = float(np.hypot(gt_vp.x - 320, gt_vp.y - 240))`.
Both are stored per-frame in the `FrameMetrics` dataclass within `self.metrics_history`.

## 4. Tk GUI mechanism

The GUI (`fsoc/gui/app.py`) runs the engine in a background `threading.Thread` (`self.worker_thread`).
The GUI builds its UI (viewport, menus) in the main thread during `__init__`.
According to the Tkinter rules, widget updates must happen from the main thread, likely via polling (`root.after`).

## 5. Benchmark runner returns

- Returns a dictionary mapping benchmark type to a list of `ScenarioKPIs` (e.g., `{"benchmark_1": [...], "benchmark_2": [...]}`).
- `ScenarioKPIs` contains `mean_err`, `acq_s`, `lock_pct`, `fps`, etc.
- It can run headless using `ClosedLoopEngine.run(max_frames)`.
- It saves R27 (JSON summary), R29 (tracking CSV), R30 (per-scenario error CSV) automatically.

## 6. Camera model properties

- `cfg.camera.px_per_deg_x` and `px_per_deg_y` are available.
- Pan and tilt angles are exposed via `self.camera.pan_deg` and `self.camera.tilt_deg` each frame.

## 7. Determinism

The simulation seems deterministic if the `cfg.pipeline.seed` is set (passed to DisturbanceEngine, ParticleFilter, etc.).
Synthetic test videos use a seeded `numpy.random.RandomState`.

## Contradictions / Differences from the plan

- In Phase 8, the calibration slot needs to be explicitly added to `engine.py` as it doesn't exist yet.
- The `FrameMetrics` history contains the per-frame error series, but the `ScenarioKPIs` dataclass returned by `MetricsEvaluator.evaluate()` might not include the full array/list of errors (only summary stats). Phase 6 might require modifying `ScenarioKPIs` or fetching `err_series` directly from the `MetricsEvaluator`.
- The GUI already runs the engine in a separate thread. This aligns with the plan's warning: `Poll with after(); never call widgets from the engine thread`.

---
## Proposed Edits for Phase 1

1. Create `fsoc_engine/src/fsoc/plugins/registry.py`:
   Define `FUNCS`, `ACTIVE`, `STATE`, `PARAMS`, `STATS`. Add `call()`, `register()`, `activate()`, `reset_all()`.

2. Create `fsoc_engine/src/fsoc/plugins/defaults.py`:
   ```python
   def default_tracking(meas, dt, state, params):
       # Adapter for IMMTracker/KalmanTracker + ParticleFilter
       ...
   ```
   *Note: Since the engine instantiates `self.kalman` and `self.particle_filter` in `__init__`, the default adapter needs access to them, or the state dictionary should hold them.*

3. Modify `engine.py` `__init__`:
   ```python
   from .plugins import defaults, registry
   registry.reset_all() # Ensure clean state
   ```

4. Modify `engine.py` `step()`:
   Replace tracker block with:
   ```python
   meas = {"x": best_det.x, "y": best_det.y, "confidence": best_det.score, ...} if best_det else None
   track = registry.call("tracking", meas, self.cfg.pipeline.dt)
   # Adapt `track` dict back into a TrackState to feed the rest of the engine
   ```

5. Create `tests/test_plugins_registry.py` to test the registry functions and exception fallback.
