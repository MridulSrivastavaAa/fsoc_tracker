# 02 – Design Document
**Project:** AI-Based Virtual Camera Tracking System for FSOC Coarse Alignment (PS 26169)
**Version:** 0.1 (draft)

## 1. Problem & Scope
Coarse alignment of a mobile FSOC terminal: locate a beacon on a large virtual screen, keep it within the camera FOV and near its centre, while the feed is degraded by noise, jitter, platform motion and atmosphere. Fine pointing is out of scope. Input is either a generated scene or a .mp4 of the full screen.

## 2. Key Numbers
| Quantity | Value | Derivation |
|---|---|---|
| Camera | 640 x 480 px, 4° x 3° | given |
| Angular scale | **160 px/°** | 640 / 4 |
| Screen | 2000 x 2000 px = **12.5° x 12.5°** | 2000 / 160 |
| Max pan/tilt rate | 5–10 °/s = 800–1600 px/s | x160 |
| Per-frame slew @30 Hz | 26.7–53 px/frame | |
| Worst slew (centre to edge, per axis) | 1000 px = 6.25° -> **1.25 s @5°/s**, 0.63 s @10°/s | axes move independently |
| Frame budget | 33 ms @30 FPS; hard floor 50 ms @20 FPS | |

**Consequence:** at 5°/s the slew alone can use ~1.25 s of the 2 s acquisition limit. Detection of the beacon on the *whole* screen must therefore happen in the first few frames (wide search), not by blind scanning. **Assumption A1 (to confirm with mentors):** the full screen (or a downscaled version) is observable for acquisition; otherwise acquisition needs a scan and the 2 s target is at risk. In video mode the full-screen video is given, which supports A1.

## 3. System Architecture
```
FrameSource -> VirtualCamera(viewport) -> DisturbanceEngine -> Preprocess
   -> Detector(+Verifier CNN) -> Tracker(Kalman) -> StateMachine
   -> Controller(PID + limits) -> VirtualCamera (closed loop)
   \-> Metrics/Logger/GUI (tap on every stage)
```
- **Closed loop:** camera state at frame *k* determines which crop is seen at *k+1*.
- **Video mode:** the "PTZ bypass" means the crop/pan-tilt is virtual over the given full-screen video; the pipeline output is the estimated beacon position per frame.
- **Threading:** engine thread (pipeline) + GUI thread; frames passed by a lock-free queue (drop-oldest for GUI so the engine never stalls).

## 4. Simulation Design
### 4.1 Scene
2000x2000 uint8 canvas. Background = low-frequency Perlin/fractal noise + faint stars/clouds + optional static distractors (bright blobs, hot pixels) to force real discrimination.
### 4.2 Target
Square (default), circle, cross; size 5–20 px (default 10x10); brightness with Gaussian PSF blur (sigma 0.5–2 px) so the centroid is sub-pixel meaningful. Initial position random by default.
### 4.3 Motion models (position p(t), pixels)
| Model | Definition |
|---|---|
| Straight | p0 + v t, reflect at screen borders |
| Circular | c + R(cos wt, sin wt) |
| Figure-8 | c + (A sin wt, B sin 2wt) |
| Random | random-walk on velocity with bounded acceleration |
| Spiral (opt) | c + (r0 + k t)(cos wt, sin wt) |
| Sinusoidal (opt) | x = x0 + v t, y = y0 + A sin(wt) |
| User-defined | CSV/point list, interpolated |

Target speed is bounded so that it stays trackable by the camera (default <= 80 % of max slew rate), configurable up to stress values.

## 5. Virtual Camera
State: `(pan, tilt)` in degrees (or equivalently viewport centre `(cx, cy)` px). Render = crop of 640x480 around `(cx, cy)`; near borders, clamp centre so the crop stays on screen. Initial position: screen centre. FOV and resolution user-defined; scale = `res_x / fov_x`.
**Pan/tilt actuator model:** commanded rate clipped to `max_rate`; acceleration limit (default 30 °/s²); first-order lag + fixed latency (1 frame) to mimic a real gimbal; update >= 20 Hz.

## 6. Disturbance Engine
Applied in this fixed order (physically motivated):
1. **Atmosphere** (contrast/brightness): `I' = alpha*I + beta` — Clear (1.0,0), Haze (0.7,+15), Fog (0.45,+35 plus blur sigma 1.5), Rain (streak overlay + 0.8,0 + random streaks), Low light (0.4,-10 plus stronger shot noise). Turbulence: beam wander (slow random offset), scintillation (multiplicative log-normal intensity flicker), blur.
2. **Camera jitter:** per-frame random shift, uniform/Gaussian, up to ±20 px, applied as sub-pixel affine translation.
3. **Platform motion:** slow low-frequency additive drift, up to ±20 px/frame, Linear (mandatory), circular/random/spiral/fig-8 (optional).
4. **Noise:** Salt & Pepper (density up to ~10 %), Gaussian (sigma up to 20), Poisson (shot noise). Any subset selectable.

Each disturbance exposes `enabled`, `strength`, and its own RNG stream.

## 7. Perception
### 7.1 Preprocessing
- Median 3x3 (kills salt & pepper), optional Gaussian 3x3.
- Background estimate via large-kernel blur or running median; subtract for local contrast.
- Robust threshold: `T = median + k * MAD` (adapts to fog/low light), k tunable.
### 7.2 Classical detector
Threshold -> connected components -> filter by area/aspect -> **intensity-weighted centroid** (sub-pixel) -> candidate list with features `(area, peak, contrast, compactness)`.
### 7.3 Wide-area acquisition
Downscale the full frame (x4 -> 500x500), same blob logic with lower threshold, pick best candidates, convert to full-screen coordinates, command slew. Refine once the beacon is inside the viewport.
### 7.4 CNN verifier (AI layer 1)
- Input: 32x32 patch around each candidate. Output: p(beacon).
- Architecture: Conv(1->8,3)-ReLU-Conv(8->16,3,s2)-ReLU-Conv(16->32,3,s2)-ReLU-GAP-FC(32->1); ~7k parameters; INT8/FP16 ONNX; <1 ms for a batch of 8 on CPU.
- Purpose: reject noise clusters, rain streaks, static distractors that the threshold cannot separate.
- Also used to choose the beacon among several candidates at acquisition.
### 7.5 Optional AI layer 2: motion predictor
GRU/MLP on last N=10 track positions -> next position. Fused with Kalman prediction (use only if it beats Kalman on validation, otherwise dropped and reported honestly).

## 8. Tracking
Kalman filter, state `[x, y, vx, vy]`, constant-velocity model (optionally constant-acceleration for figure-8/circular).
- Measurement noise R adapted from detection SNR/CNN score.
- Process noise Q adapted from innovation statistics (NIS).
- **Gating:** Mahalanobis gate around the prediction; picks the candidate closest to prediction.
- **Coasting:** if no valid detection, predict for up to N frames (default 15) before declaring LOST.
- **ROI processing:** once tracking, run the detector only inside a window around prediction -> big FPS gain.
- Multi-target (optional): Hungarian assignment, one Kalman per track, "designated" target selected by user/ID.
- Camera-motion compensation: target position in screen coordinates = viewport position + camera centre, so tracking is done in the world frame and camera ego-motion doesn't corrupt velocity.

## 9. Control
Error `e = target_screen_pos_predicted - camera_centre` (px -> deg).
- PID per axis with anti-windup, derivative on measurement, and **feed-forward of Kalman velocity** (target velocity + platform motion) to cut steady lag.
- Rate saturation (`max_pan`, `max_tilt`), accel limit, deadband ~1 px.
- Gain scheduling: aggressive in ACQUIRE (large error), smoother in TRACK.

### 9.1 State machine
| State | Entry | Action | Exit |
|---|---|---|---|
| SEARCH | start / target not found | wide-area detect; if none, scan pattern (spiral) | verified candidate -> ACQUIRE |
| ACQUIRE | candidate found | max-rate slew toward it, initialise Kalman | beacon in FOV & confirmed M of N frames -> TRACK; timeout -> SEARCH |
| TRACK | confirmed | PID + feed-forward, ROI detect | no detection K frames -> LOST |
| LOST | detections missing | coast on Kalman prediction, widen ROI | re-detected -> TRACK (log re-acq time); coast limit hit -> REACQUIRE |
| REACQUIRE | coasting failed | wide-area search around last position, then full screen | found -> ACQUIRE; else SEARCH |

## 10. Metrics (definitions used by logger and benchmarks)
- **Centroiding error** e_k = || est_k - gt_k || (px, in screen coords) — per frame.
- **Tracking error (control)** = || target - viewport centre || (px).
- **RMSE** = sqrt(mean(e_k²)); mean, max, p95 also reported.
- **Acquisition time** = time from start to first M-of-N confirmed lock.
- **Re-acquisition time** = time from LOST entry to TRACK re-entry (list + max).
- **Lock retention rate** = frames in TRACK / frames after first lock.
- **Target loss %** = frames where target not in FOV or state != TRACK / total frames.
- **FPS / processing time** = per-frame wall time, module-wise breakdown, mean & p95.

## 11. GUI (PySide6 + pyqtgraph)
Panels: live viewport with overlays (detection box, Kalman prediction, crosshair, FOV), full-screen minimap with camera rectangle and ground truth, config panel (target, motion, disturbances, camera limits, algorithm toggles), real-time plots (error, FPS, state timeline, lock %), buttons (start/pause/step/reset/load video/save report/run benchmark). Default and "expert" layouts.

## 12. Timing Budget (per frame, CPU only)
| Stage | Budget (ms) |
|---|---|
| Scene render + crop | 5 |
| Disturbances | 6 |
| Preprocess | 3 |
| Detect (ROI) | 3 |
| CNN verify | 2 |
| Kalman + control | 1 |
| Logging | 1 |
| **Engine total** | **~21 (≈47 FPS)** |
| GUI (separate thread) | not counted |

Full-screen wide search (~15–25 ms) runs only in SEARCH/REACQUIRE.
Optimisations: uint8 everywhere, preallocated buffers, OpenCV ops, ROI, Numba on hotspots.

## 13. Testing Strategy (summary)
Unit (motion, camera maths, Kalman consistency), integration (scenario suite: 4 motions x 5 atmospheres x noise levels x jitter levels), benchmark (timing and accuracy regression on fixed seeds), video-mode tests on self-generated .mp4 (H.264, 30 fps) with re-encoding artefacts.

## 14. Design Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Heavy S&P noise creates false blobs | median filter + morphology + CNN verifier |
| ±20 px/frame jitter vs slew limit | world-frame tracking + feed-forward + gating |
| mp4 compression smears small beacon | train/test with compression augmentation |
| Similar distractors | CNN + motion consistency (Kalman gating) |
| FPS drop on weak PC | ROI, downscale, ONNX, disable GUI overlays |
| Beacon leaves FOV during fast motion | wide search from full-screen view + coasting |
