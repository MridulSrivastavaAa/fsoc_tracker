# 01 – Project Structure
**Project:** AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals (SIH PS 26169, ISRO/SAC)

## 1. Guiding Rules
1. **Every input goes through a `FrameSource`** (SimulatedSource or VideoFileSource). No module may know which one is active.
2. **All parameters live in YAML config** (`configs/`). No magic numbers in code.
3. **Engine is GUI-independent.** The pipeline runs headless (CLI) for benchmarks; the GUI is only a viewer/controller.
4. **One responsibility per module**; modules communicate through typed dataclasses (`core/types.py`).
5. **Everything is seeded** so any scenario or dataset is reproducible.

## 2. Repository Layout
```
fsoc_tracker/
├── README.md
├── pyproject.toml / requirements.txt
├── configs/
│   ├── default.yaml              # all default parameters (from PS table)
│   ├── scenarios/                # benchmark scenarios (one yaml each)
│   └── datagen.yaml              # data generation config (see file 04)
│
├── src/fsoc/
│   ├── core/
│   │   ├── config.py             # load/validate YAML (pydantic)
│   │   ├── types.py              # Frame, Detection, TrackState, Command, Metrics dataclasses
│   │   ├── frame_source.py       # abstract FrameSource
│   │   ├── camera.py             # VirtualCamera: viewport crop, pan/tilt state, FOV<->pixel maths
│   │   ├── pipeline.py           # main loop wiring all stages
│   │   └── state_machine.py      # SEARCH/ACQUIRE/TRACK/LOST/REACQUIRE
│   │
│   ├── simulation/
│   │   ├── scene.py              # 2000x2000 canvas, background generation
│   │   ├── targets.py            # Target (shape, size, brightness), multi-target support
│   │   ├── motion_models.py      # line, circle, fig-8, random, spiral, sinusoidal, user-defined
│   │   └── sim_source.py         # SimulatedSource(FrameSource)
│   │
│   ├── video/
│   │   └── video_source.py       # VideoFileSource(FrameSource) for .mp4 @30fps
│   │
│   ├── disturbances/
│   │   ├── noise.py              # salt&pepper, gaussian, poisson
│   │   ├── jitter.py             # camera jitter (+-20 px/frame)
│   │   ├── platform_motion.py    # linear (mandatory), circular, random, spiral, fig-8
│   │   ├── atmosphere.py         # clear, haze, fog, rain, low light, turbulence (blur/wander/scintillation)
│   │   └── engine.py             # composes enabled disturbances in fixed order
│   │
│   ├── vision/
│   │   ├── preprocess.py         # median filter, normalisation, background subtraction
│   │   ├── detector.py           # threshold + connected components + weighted centroid
│   │   ├── wide_search.py        # downscaled full-screen search for acquisition
│   │   ├── cnn_verifier.py       # ONNX-runtime candidate classifier
│   │   └── multi_target.py       # data association (Hungarian) for optional multi-target
│   │
│   ├── tracking/
│   │   ├── kalman.py             # CV Kalman filter, adaptive noise
│   │   └── tracker.py            # gating, coasting, track confidence
│   │
│   ├── control/
│   │   ├── pid.py                # PID + anti-windup
│   │   └── pan_tilt_model.py     # max speed, accel limit, latency, deadband
│   │
│   ├── metrics/
│   │   ├── metrics.py            # centroid error, RMSE, acquisition/re-acq, lock rate, FPS
│   │   ├── logger.py             # per-frame CSV + JSON summary
│   │   └── report.py             # auto performance report (HTML/PDF)
│   │
│   ├── gui/
│   │   ├── main_window.py        # PySide6 main window
│   │   ├── config_panel.py       # sliders/dropdowns for every parameter
│   │   ├── video_view.py         # live feed + overlays
│   │   └── plots.py              # pyqtgraph error/FPS/state plots
│   │
│   └── cli/
│       ├── run_scenario.py       # headless run for Benchmark-1
│       ├── run_video.py          # headless .mp4 run for Benchmark-2 (outputs frame,x,y,conf,state)
│       └── generate_data.py      # dataset generator entry point
│
├── training/
│   ├── datasets.py               # PyTorch datasets reading shards
│   ├── model_verifier.py         # tiny CNN
│   ├── model_motion.py           # optional GRU/MLP motion predictor
│   ├── train_verifier.py
│   ├── train_motion.py
│   ├── export_onnx.py
│   └── evaluate.py
│
├── models/                       # exported .onnx files (shipped with exe)
├── data/                         # NOT in git (up to ~40 GB)
│   ├── patches/  frames/  sequences/  videos/  manifests/
├── tests/
│   ├── unit/                     # motion models, camera maths, kalman, pid
│   ├── integration/              # full pipeline on scenarios
│   └── benchmark/                # timing + accuracy regression
├── outputs/                      # logs, reports, screenshots (git-ignored)
├── docs/                         # design, PDR, technical report, user manual
├── packaging/
│   ├── fsoc.spec                 # PyInstaller spec
│   └── build.bat / build.sh
└── main.py                       # GUI entry
```

## 3. Module Interfaces (contracts)
| Interface | Signature | Notes |
|---|---|---|
| `FrameSource` | `next_frame() -> FullFrame`, `ground_truth() -> list[Point] \| None` | video mode returns None |
| `VirtualCamera` | `render(full_frame) -> np.uint8[480,640]`, `apply(cmd)`, `state -> (pan,tilt)` | viewport crop + wrap/clip at screen edge |
| `DisturbanceEngine` | `apply(img, t) -> img` | order: atmosphere -> platform/jitter shift -> noise |
| `Detector` | `detect(img) -> list[Detection(x,y,intensity,area,score)]` | sub-pixel centroid |
| `Verifier` | `score(patches) -> float[]` | ONNX, batched |
| `Tracker` | `update(dets, dt) -> TrackState(x,y,vx,vy,conf)` | coasts if no detection |
| `Controller` | `step(track, cam_state, dt) -> Command(pan_rate,tilt_rate)` | limits applied |
| `Logger` | `log(frame_idx, ...)` | per-frame CSV |

## 4. Coding Conventions
- Python 3.10+, type hints, `black` + `ruff`, docstrings on every public function.
- Coordinates: image (x right, y down) in pixels; angles in degrees; conversion only in `camera.py`.
- Time base: `dt = 1/fps` from config, never `time.time()` in simulation logic (deterministic).
- Git: `main` (stable), `dev`, feature branches; PR + 1 review; tag milestones (`v0.1-sim`, `v0.5-core`, `v1.0-submit`).

## 5. Output Contracts
**Per-frame CSV:** `frame, t, state, est_x, est_y, gt_x, gt_y, err_px, conf, locked, proc_ms, pan, tilt`
**Video mode CSV:** `frame, x, y, confidence, state`
**Summary JSON:** duration, fps_mean/min, acquisition_time, reacq_times[], err_mean/max/rmse, lock_retention_pct, target_loss_pct, proc_ms_mean/p95.

## 6. Build Order
Follow the 12-step order: config -> sim+targets -> camera -> video source -> disturbances -> detector -> Kalman -> PID+state machine (**core milestone**) -> metrics -> GUI -> CNN/multi-target -> packaging/docs.
