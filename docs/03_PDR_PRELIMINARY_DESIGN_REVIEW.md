# 03 – Preliminary Design Review (PDR)
**Project:** AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals
**PS ID:** 26169 | **Org:** ISRO (SAC) | **Category:** Software | **Theme:** Smart Automation
**Team:** _<fill>_ | **Date:** _<fill>_ | **Revision:** 0.1

## 1. Purpose of this review
Confirm that the problem is understood, requirements are captured and traceable, the chosen architecture can meet the performance targets, and risks/open items are known **before** implementation begins.

## 2. Problem Understanding (one paragraph)
An FSOC terminal must find a remote beacon and keep it in the camera FOV (coarse PAT) before fine pointing can start. We build a software-only system: virtual scene + moving beacon(s) + virtual pan-tilt camera + disturbances, with automatic detection, tracking and closed-loop camera control, live statistics and an auto-generated performance log. It must also run on organiser-provided .mp4 videos (full screen, noise, moving beacon) as input.

## 3. Requirements & Traceability
Legend: M = mandatory, O = optional. Verification: T = test, D = demo, I = inspection, A = analysis.

| ID | Requirement (source: PS table) | Type | Design element | Verification |
|---|---|---|---|---|
| R1 | Screen >= 2000x2000 px (user-defined optional) | M | `simulation/scene.py` | I, D |
| R2 | Monochrome FPA camera, colour optional | M/O | `core/camera.py` | I |
| R3 | Camera resolution 640x480 (user-defined) | M | `core/camera.py`, config | T |
| R4 | FOV default 4°x3°, user-defined | M | camera scale 160 px/° | T |
| R5 | Camera update >= 30 Hz | M | pipeline clock | T |
| R6 | Initial camera position = screen centre | M | camera init | T |
| R7 | Beacon spot target; 1 mandatory, multiple optional | M/O | `targets.py`, `multi_target.py` | D |
| R8 | Shape (default square), size 5–20 px (default 10) | M | `targets.py` | T |
| R9 | Initial location user-defined, default random | M | config, RNG | T |
| R10 | >= 4 selectable motions (line, circle, fig-8, random) + optional spiral, sinusoidal, user | M/O | `motion_models.py` | T |
| R11 | Max pan/tilt 5–10 °/s (default 5) | M | `pan_tilt_model.py` | T |
| R12 | Control update >= 20 Hz | M | pipeline | T |
| R13 | Acquisition time <= 2 s | M | wide-area search + fast slew | T, A |
| R14 | Tracking error <= 10 px | M | Kalman + PID + FF | T |
| R15 | Target loss < 5 % | M | coasting, ROI, CNN | T |
| R16 | Re-acquisition time <= 1 s | M | LOST/REACQUIRE logic | T |
| R17 | Processing speed >= 20 FPS | M | ROI, ONNX, optimisation | T |
| R18 | Noise: S&P (~10 %), Gaussian, Poisson; selectable | M | `noise.py` | T |
| R19 | Noise sigma up to 20 | M | config | T |
| R20 | Camera jitter up to ±20 px/frame | M | `jitter.py` | T |
| R21 | Atmosphere: clear/haze/fog/rain/low light | M | `atmosphere.py` | T |
| R22 | Platform motion up to ±20 px/frame; linear mandatory | M | `platform_motion.py` | T |
| R23 | Standalone executable | M | PyInstaller | D |
| R24 | Documented modular source code | M | structure, docstrings | I |
| R25 | Technical report 10–15 pages | M | docs | I |
| R26 | User manual (+ optional 3–5 min video) | M/O | docs | I |
| R27 | Auto performance log (duration, FPS, acquisition, avg/max error, lock retention, processing time) | M | `metrics/` | T |
| R28 | Real-time performance/statistics display | M | GUI plots | D |
| R29 | .mp4 (30 fps) input, PTZ bypassed, coarse pointing runs on it | M (Benchmark-2) | `video_source.py`, `run_video.py` | T |
| R30 | Log of centroiding error per scenario | M (Benchmark-1) | `logger.py` | T |

## 4. Selected Design (summary)
- **Pipeline:** FrameSource -> VirtualCamera -> Disturbances -> Preprocess -> Detector(+CNN) -> Kalman -> State machine -> PID+limits -> camera.
- **Hybrid perception:** classical sub-pixel centroid detector for speed/accuracy + tiny CNN verifier (ONNX) for robustness. Optional learned motion predictor, kept only if it beats Kalman.
- **Control:** PID with Kalman-velocity feed-forward, rate and acceleration limits, 5-state machine.
- **Stack:** Python, OpenCV, NumPy, PyTorch (training only), ONNX Runtime (inference), PySide6/pyqtgraph, PyInstaller.
Details: see `02_DESIGN_DOCUMENT.md` and `01_PROJECT_STRUCTURE.md`.

## 5. Feasibility Analysis
| Item | Analysis | Verdict |
|---|---|---|
| Scale | 640/4° = 160 px/°; screen = 12.5° | fixed |
| Slew | 1000 px = 6.25° -> 1.25 s @5°/s (0.63 s @10°/s) | acquisition OK only if target is localised in the first ~0.5 s |
| Disturbance vs actuator | ±20 px/frame = 600 px/s = 3.75°/s < 5°/s max, but leaves only ~1.25°/s for target motion | tight at 5°/s; feed-forward is essential; default disturbance is not always at max |
| Compute | ~21 ms/frame budget on CPU (~47 FPS) | meets >= 20 FPS with margin |
| mp4 input | compression alters noise/beacon appearance | augment training data with H.264 |
| Tracking error <= 10 px | at 160 px/° this is 0.06° | feasible with sub-pixel centroid + Kalman |

## 6. Verification Plan
1. **Unit tests** on maths (px<->deg, motion models, Kalman NEES/NIS, PID limits).
2. **Scenario matrix** (fixed seeds): 4 motions x 5 atmospheres x 4 noise levels x 3 jitter levels x 2 platform motions; pass criteria = R13–R17.
3. **Stress tests:** max jitter + 10 % S&P + fog + fast target; target leaves FOV; target disappears 1 s and returns.
4. **Video benchmark:** self-generated mp4s (H.264, several bitrates) evaluated against ground truth.
5. **Performance profiling** on a mid-range laptop; report FPS mean/p95.
6. **Clean-machine exe test** (no Python installed).

## 7. Development Plan / Milestones
| Milestone | Content | Exit criterion |
|---|---|---|
| M0 | Kick-off, config, repo, mentor questions | repo + config schema ready |
| M1 | Sim + targets + motions + camera + video source | dot moves, GT saved, mp4 plays through same pipeline |
| M2 | Disturbances + detector | beacon found under noise (>= 95 % frames, classical) |
| M3 | Kalman + PID + state machine (**core**) | camera follows target headless; R13–R17 mostly met |
| M4 | Metrics + logger + report | auto report generated |
| M5 | GUI | full demo flow |
| M6 | Data generation + CNN + (optional) multi-target | CNN beats classical in heavy noise |
| M7 | Optimisation + exe + full test matrix | all requirements verified |
| M8 | Report + manual + video | submission package |

## 8. Team & Responsibilities (edit to team size)
| Role | Scope |
|---|---|
| A – Simulation | scene, targets, motions, camera, video source, disturbances, data generator |
| B – Perception/AI | detector, wide search, CNN, Kalman, motion predictor |
| C – Control/Metrics | PID, state machine, logging, reports, benchmark tools |
| D – GUI/Packaging | GUI, exe, user manual |
| All | tests, technical report, presentation |

## 9. Risk Register
| # | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| 1 | Acquisition > 2 s (slew-limited) | M | H | wide-area detect, max-rate slew, gain scheduling | B/C |
| 2 | False detections in heavy noise/rain | H | H | median + CNN verifier + Kalman gating | B |
| 3 | FPS < 20 on evaluator PC | M | H | ROI, ONNX INT8, profiling, low-overlay mode | A/D |
| 4 | mp4 format/behaviour differs from assumption | M | H | ask mentors early; robust reader; compression augmentation | A |
| 5 | Overfitting CNN to our simulator | M | M | domain randomisation, held-out generators, mp4 artefacts | B |
| 6 | Data volume (40 GB) slows iteration | M | M | shard format, small dev subset (1 GB) for fast loops | A |
| 7 | exe size/startup/antivirus flags | M | L | exclude torch from exe (ONNX only), one-dir build | D |
| 8 | Docs left to last | H | M | doc stubs each milestone, screenshots auto-saved | All |
| 9 | Scope creep (multi-target, extras) | M | M | mandatory first; optional only after M4 | Lead |

## 10. Open Items / Questions for Mentors
1. During acquisition, is the full 2000x2000 screen observable (even downscaled), or only the 640x480 viewport?
2. Exact mp4 spec (resolution, codec, single or multiple beacons, distractors, ground-truth format for comparison)?
3. Is "centroiding error" measured in screen pixels against the beacon centre in the screen frame?
4. Expected units/format of the required output log in video mode?
5. Are Benchmark-1 scenarios supplied as config files or specified verbally (parameters)?
6. Is GPU available on the evaluation machine? (We assume CPU only.)
7. Definition of "lock" (beacon inside FOV vs within N px of centre) for lock retention rate?

## 11. Entry/Exit Criteria
**PDR exit:** requirements agreed, open items 1–3 answered or assumptions recorded, architecture frozen for M1–M3, risk owners assigned.
**Go/No-go for CDR (after M3):** core loop meets R13–R17 on the clean and moderate-noise scenarios.

## 12. Action Items
| Action | Owner | Due |
|---|---|---|
| Email mentors with Section 10 | Lead | Day 1 |
| Repo + config schema | A | Day 2 |
| Implement M1 | A | Week 1 |
| Datagen v0 (1 GB dev set) | A/B | Week 2 |
| Baseline classical detector + Kalman | B | Week 2 |
