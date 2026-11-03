# FSOC Virtual Camera Tracking System — Project Roadmap & Execution Plan
**Problem Statement ID:** 26169 (Smart India Hackathon / ISRO - SAC)  
**Title:** Development of an AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals  
**Document Version:** 1.0 (Master Execution Roadmap)  

---

## 1. Executive Summary & Starting Strategy

### Kaha Se Shuru Karein (Where to Start)?
Aksar log seedha GUI ya AI model train karne lagte hain, jisse project baad me crash ho jata hai. Sahi engineering approach **Bottom-Up Pipeline** hai:
1. **Starting Point:** **Phase 1 (Virtual Simulation Engine & Core Math)**
   - Pehle $2000 \times 2000$ ka virtual canvas banega.
   - Us par beacon target ke 4 mandatory motion models chalenge (Straight line, Circle, Figure-of-8, Random).
   - $640 \times 480$ ka movable virtual camera viewport crop banega.
   - Jaise hi hum camera ko canvas par move kar sakenge aur ground-truth position log kar sakenge, hamari solid foundation ready ho jayegi.
2. **Ending Point:** **Phase 8 (Standalone `.exe` Packaged App + Benchmark-1 & Benchmark-2 Validation + 10-15 Page Technical Report)**.
3. **Extra Feature Slot:** **Phase 7** ko specially reserve rakha gaya hai jahan aap apna extra custom feature add karenge.

---

## 2. End-to-End Phased Roadmap

```
Phase 0: Environment & Core Types Setup
   │
   ▼
Phase 1: Simulation Canvas, Target Motions & Virtual Camera (STARTING POINT)
   │
   ▼
Phase 2: Disturbance Engine (Noise/Jitter/Atmosphere) & Video Bypass (.mp4)
   │
   ▼
Phase 3: Perception Engine (Classical Sub-Pixel Centroid + ONNX CNN Verifier)
   │
   ▼
Phase 4: Tracking & Control (Kalman Filter + 5-State Machine + Feed-forward PID)
   │
   ▼
Phase 5: Telemetry, Auto-Logging & Benchmark Scripts (Benchmark 1 & 2)
   │
   ▼
Phase 6: Interactive Desktop GUI (PySide6 + pyqtgraph Real-time Analytics)
   │
   ▼
Phase 7: Custom Feature Extension (USER's EXTRA FEATURE)
   │
   ▼
Phase 8: Packaging (.exe), Final Benchmarking & Submission Deliverables
```

---

## 3. Detailed Phase Breakdown

### Phase 0: Foundations & Project Setup
- **Goal:** Clean project structure, dependencies, typed dataclasses, and configuration management.
- **Key Modules:**
  - `configs/default.yaml`: All default parameters from ISRO table (canvas 2000x2000, FOV 4°x3°, speeds 5°/s, etc.).
  - `src/fsoc/core/types.py`: Typed contracts (`Point`, `Frame`, `Detection`, `TrackState`, `CameraCommand`, `PerformanceMetrics`).
  - `src/fsoc/core/config.py`: Pydantic/dataclass config validator.
- **Deliverables:** Verified environment, imports working without errors.

---

### Phase 1: Simulation Engine & Virtual Camera (THE STARTING POINT)
- **Goal:** Ground-truth virtual world and camera kinematics.
- **Key Modules:**
  - `src/fsoc/simulation/scene.py`: 2000x2000 canvas generator with realistic space/sky background and optional static distractors.
  - `src/fsoc/simulation/targets.py`: Optical beacon spot generator (size 5–20 px, Gaussian PSF blur for sub-pixel accuracy).
  - `src/fsoc/simulation/motion_models.py`: 
    - *Mandatory:* Straight Line, Circular, Figure-of-8, Bounded Random Walk.
    - *Optional:* Spiral, Sinusoidal, User-defined waypoints.
  - `src/fsoc/core/camera.py`: Virtual pan-tilt camera with $640 \times 480$ viewport crop, $160\text{ px/}^\circ$ angular scale, gimbal rate limit ($5^\circ/\text{s}$), acceleration limit ($30^\circ/\text{s}^2$), and 1-frame latency.
  - `src/fsoc/core/frame_source.py` & `src/fsoc/simulation/sim_source.py`: Abstract `FrameSource` interface.
- **Verification:** Unit tests confirming target trajectory math, screen wrapping, and camera coordinate conversions.

---

### Phase 2: Disturbances Engine & Video Bypass Source
- **Goal:** Simulate real-world operational challenges and fulfill Benchmark-2 requirement.
- **Key Modules:**
  - `src/fsoc/disturbances/noise.py`: Salt & Pepper (~10%), Gaussian ($\sigma \le 20$), and Poisson noise.
  - `src/fsoc/disturbances/jitter.py`: Camera platform vibrations ($\pm 20\text{ px/frame}$).
  - `src/fsoc/disturbances/platform_motion.py`: Linear platform drift ($\pm 20\text{ px/frame}$) + optional nonlinear motion.
  - `src/fsoc/disturbances/atmosphere.py`: Clear, Haze, Fog, Rain streaks, Low-light, and Turbulence (beam wander, scintillation, blur).
  - `src/fsoc/video/video_source.py`: `VideoFileSource` to ingest pre-recorded `.mp4` video feeds @ 30 FPS, bypassing virtual PTZ for Benchmark-2.
- **Verification:** Visual and quantitative verification of disturbance layers.

---

### Phase 3: Perception & Vision Pipeline (Classical + AI Verifier)
- **Goal:** High-speed, robust beacon detection under extreme noise and low SNR.
- **Key Modules:**
  - `src/fsoc/vision/preprocess.py`: Fast 3x3 median filter (removes S&P noise), dynamic background subtraction, MAD thresholding.
  - `src/fsoc/vision/detector.py`: Connected components analysis, intensity-weighted sub-pixel centroid calculation.
  - `src/fsoc/vision/wide_search.py`: 4x downscaled full-scene search ($500 \times 500$) for rapid target acquisition ($< 2$ seconds).
  - `src/fsoc/vision/cnn_verifier.py`: Ultra-lightweight ONNX CNN (~7k parameters, $< 1\text{ ms}$ on CPU) to classify 32x32 patches and reject false positives (noise clumps, rain streaks, stars).
- **Verification:** Precision/Recall $> 98\%$ on noisy test frames; detection time $< 5\text{ ms}$.

---

### Phase 4: State Machine, Kalman Tracking & Closed-Loop Control
- **Goal:** Autonomous tracking, lost-target re-acquisition, and smooth camera pointing.
- **Key Modules:**
  - `src/fsoc/tracking/kalman.py`: 2D Constant Velocity Kalman Filter with adaptive covariance and Mahalanobis gating.
  - `src/fsoc/tracking/tracker.py`: ROI-based tracking (speeds up FPS), coasting up to 15 frames during beacon fade.
  - `src/fsoc/core/state_machine.py`: 5 states: `SEARCH` $\to$ `ACQUIRE` $\to$ `TRACK` $\to$ `LOST` $\to$ `REACQUIRE`.
  - `src/fsoc/control/pid.py`: Dual-axis PID with anti-windup, derivative filtering, and **target velocity feed-forward** to eliminate steady-state tracking lag.
- **Verification:** Tracking error $\le 10$ pixels; re-acquisition time $\le 1$ second; lock retention $> 95\%$.

---

### Phase 5: Metrics, Logging & Benchmark Automation
- **Goal:** Automatically record performance logs and evaluate Benchmark-1 & Benchmark-2.
- **Key Modules:**
  - `src/fsoc/metrics/metrics.py`: Computes RMSE, Mean/Max centroiding error, Lock retention %, Target loss %, Acquisition time, Processing FPS.
  - `src/fsoc/metrics/logger.py`: High-speed per-frame CSV logger + summary JSON.
  - `src/fsoc/metrics/report.py`: Automated HTML/PDF performance report generation.
  - `src/fsoc/cli/run_scenario.py`: Benchmark-1 CLI runner (runs any YAML scenario headlessly).
  - `src/fsoc/cli/run_video.py`: Benchmark-2 CLI runner (takes `.mp4` video, outputs `frame, x, y, confidence, state`).
- **Verification:** Regression test on standard benchmark test suite.

---

### Phase 6: Interactive Desktop GUI (PySide6 + pyqtgraph)
- **Goal:** User-friendly demonstration interface for live evaluator inspection (20% marks).
- **Key Modules:**
  - `src/fsoc/gui/main_window.py`: Multi-threaded architecture (Engine runs on high-priority thread, GUI renders smoothly without dropping simulation frames).
  - `src/fsoc/gui/video_view.py`: Viewport display with HUD overlays (target bounding box, Kalman prediction vector, boresight crosshair).
  - Minimap Radar: 2000x2000 macro view showing camera viewport position and beacon ground truth.
  - Interactive Control Panel: Live sliders for noise levels, atmospheric conditions, gimbal limits, and target motions.
  - Real-time pyqtgraph telemetry: Live plots of Tracking Error (px), Processing FPS, and State History.
- **Verification:** 30+ FPS smooth rendering on a standard laptop without GPU.

---

### Phase 7: Custom Feature Extension (USER's EXTRA FEATURE)
- **Goal:** Integrate the additional feature requested by the user to make the project stand out and win maximum innovation marks.
- **Extension Possibilities:**
  1. *Option A (3D Geospatial FSOC Link Telemetry):* 3D satellite/UAV orbit trajectory visualization using Cesium/PyVista.
  2. *Option B (Reinforcement Learning / Adaptive Gimbal Controller):* Deep Q-Learning or PPO agent to predict high-turbulence beam jitter.
  3. *Option C (Multi-Terminal Handoff):* Tracking multiple optical beacons and autonomous switching when link is blocked.
  4. *Option D (Web Dashboard / Remote Monitoring):* FastAPI + WebSockets live browser telemetry stream.
  5. *Option E:* Any custom requirement specified by the user!
- **Verification:** Seamless plug-in integration into the core pipeline without breaking existing tests.

---

### Phase 8: Packaging, Final Benchmarking & Submission Deliverables
- **Goal:** Deliver all mandatory artifacts required by ISRO / SIH evaluators.
- **Key Deliverables:**
  1. **Standalone Executable (`fsoc_tracker.exe`):** Single-folder PyInstaller bundle, verified on a clean Windows machine without Python.
  2. **Technical Report (10–15 pages):** Problem formulation, mathematical derivations, architecture, benchmark tables, and innovation highlights.
  3. **User Manual & Quickstart Guide:** Installation steps, GUI walkthrough, and parameter tuning guide.
  4. **Benchmark Verification Logs:** Pre-computed CSV/JSON logs across 12 diverse scenarios and test `.mp4` files.
  5. **Demo Video Script & Recording (3–5 minutes):** Walkthrough video showing real-time tracking, heavy noise handling, and video bypass mode.

---

## 4. Requirement Verification & KPI Matrix

| Parameter / KPI | ISRO Specification | Our Target | Validation Mechanism |
| :--- | :--- | :--- | :--- |
| **Virtual Screen** | $\ge 2000 \times 2000\text{ px}$ | $2000 \times 2000\text{ px}$ (configurable) | `scene.py` inspection |
| **Camera Viewport** | $640 \times 480\text{ px}$, $4^\circ \times 3^\circ$ | $640 \times 480\text{ px}$, $160\text{ px/}^\circ$ | `camera.py` coordinate tests |
| **Camera Update Rate** | $\ge 30\text{ Hz}$ | $30\text{ Hz}$ fixed timestep | Internal simulation clock |
| **Target Motions** | Line, Circle, Fig-8, Random | 7 motion models available | `test_motion_models.py` |
| **Pan/Tilt Limits** | $5\text{--}10^\circ/\text{s}$, update $\ge 20\text{ Hz}$ | $5^\circ/\text{s}$ default, $30\text{ Hz}$ control | `pan_tilt_model.py` rate clipping |
| **Acquisition Time** | $\le 2\text{ seconds}$ | $< 0.8\text{ seconds}$ | Wide-area downscaled search |
| **Tracking Error** | $\le 10\text{ pixels}$ | $\le 3\text{--}5\text{ pixels}$ (nominal) | Kalman + PID feed-forward |
| **Target Loss Rate** | $< 5\%$ | $< 2\%$ | Kalman coasting + CNN gating |
| **Re-acquisition Time** | $\le 1\text{ second}$ | $< 0.5\text{ seconds}$ | Fast localized re-acquisition |
| **Processing Speed** | $\ge 20\text{ FPS}$ | $\ge 40\text{ FPS}$ (CPU-only) | ROI cropping + ONNX runtime |
| **Video Input Mode** | Organiser `.mp4` @ 30 FPS | Full PTZ bypass mode | `run_video.py` on test mp4 |
| **Standalone App** | Self-contained executable | Single `.exe` via PyInstaller | Clean-machine testing |

---

## 5. Summary Timeline / Execution Milestones

* **Step 1:** Complete Phase 0 & Phase 1 (Core types, Config, Scene, Target, Virtual Camera).
* **Step 2:** Complete Phase 2 (Disturbances & Video source).
* **Step 3:** Complete Phase 3 & Phase 4 (Perception, Kalman filter, PID controller, State machine). **[Core Engine Functional]**
* **Step 4:** Complete Phase 5 (Logging & Benchmark CLI runners).
* **Step 5:** Complete Phase 6 (Interactive PySide6 GUI).
* **Step 6:** Add Phase 7 (User's extra feature).
* **Step 7:** Complete Phase 8 (Packaging to `.exe`, Technical Report, and User Manual).
