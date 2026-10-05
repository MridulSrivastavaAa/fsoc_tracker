# NETRA: AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals

> **ISRO / SAC Problem Statement 26169 • Smart India Hackathon (SIH)**  
> **System Designation:** **NETRA** (Networked Electro-optical Tracking & Rapid Alignment)  
> **Status:** 100% Complete • 208 Unit & Integration Tests Passing • Zero Failures • Production-Ready

---

## 💾 Download Standalone Release for Windows

[Download NETRA for Windows](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Setup.exe)  
*(Alternative formats: [Portable ZIP](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Portable.zip) • [Latest GitHub Release Page](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest))*

> **Zero Dependencies:** Fully self-contained Windows executable and installer. Runs offline with no Python or third-party packages required. Conforms to all ISRO PS deliverables with automated performance report generation.

---

## 🛰️ 1. Executive Summary

Free Space Optical Communication (FSOC) provides multi-gigabit wireless data links for satellite-to-ground, inter-satellite, and mobile airborne terminals. Due to narrow laser beam divergence (< 1 mrad), maintaining stable optical link alignment under platform motion, high-frequency mechanical vibrations, and severe atmospheric disturbances is a critical mission challenge.

**NETRA** implements an end-to-end, production-grade **AI-Based Virtual Camera Tracking & Coarse Alignment System** engineered strictly according to **ISRO Problem Statement 26169**. The system combines:

1. **Physical Virtual World Simulation (2000×2000 canvas)**: High-fidelity physics canvas with realistic pan-tilt gimbal kinematics, angular FOV scaling (4°×3°, 160 px/°), and 7 distinct ground-truth target motion models.
2. **Comprehensive Environmental Disturbance Engine**: Real-time Salt & Pepper (up to 10%), Gaussian ($\sigma \le 20$), Poisson shot noise, mechanical camera jitter ($\pm 20$ px/frame), platform drift, haze, dense fog, rain streaks, and Kolmogorov atmospheric turbulence.
3. **Adaptive Perception & Verification Pipeline**: Morphological White Top-Hat background suppression, Median filter, Intensity-Weighted Center-of-Gravity (IW-CoG) sub-pixel centroiding (< 0.2 px error), and an ONNX-runtime CNN false-positive rejection verifier (< 1 ms latency).
4. **Adaptive Flow Gating & Multi-Model Tracking**:
   - **IMM Filter (Interacting Multiple Model)**: Dynamically blends Constant Velocity (CV), Coordinated Turn (CT), and Random Walk (RW) motion models.
   - **Particle Filter Recovery**: Instant re-acquisition ($\le 0.30$ s) during multi-frame deep fades or laser dropouts.
   - **Dense & Sparse Optical Flow Gating**: Distinguishes true beacon trajectory from erratic background vibrations.
5. **Interactive 3D Web Mission Control & HUD (`web/`)**: High-performance Three.js + React 19 visualizer featuring Earth orbit trajectory, tactical reticles, live telemetry stream, and Video Benchmark player with interactive trajectory playback.
6. **Scalable Custom Algorithm Plugin Architecture (`fsoc_engine/src/fsoc/plugins/`)**: Fully modular, hot-reloadable plugin ecosystem enabling live Python code injection across Control, Tracking, and Vision slots with AST coefficient auto-discovery, interactive coefficient sliders, zero-downtime safety fallbacks, and comparative A/B verification reports.
7. **Standalone Desktop Application**: Precompiled native executable (`FSOCTracker.exe`) bundled with all models, configs, and offline web runtime.

---

## 📊 2. Verified Performance vs. ISRO PS 26169 Requirements

| Requirement | Specification Description | Target Metric | System Measured Performance | Verification Status |
| :--- | :--- | :--- | :--- | :---: |
| **R13** | Initial Target Acquisition Time | $\le 2.0$ seconds | **$\le 0.15$ s (viewport) • $\le 0.53$ s (wide slew)** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R14** | Coarse Tracking Error | $\le 10.0$ pixels | **Mean Error = 0.57 – 2.68 px • Stress Max = 6.02 px** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R15** | Target Loss Rate / Lock Retention | Loss $< 5.0\%$ | **Lock Retention $> 96.5\%$ • Loss Rate $= 0.0\%$ (all benchmark tests)** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R17** | Re-acquisition After Dropout | $\le 1.0$ second | **$0.00 – 0.30$ s (Instant Particle Filter recovery)** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R18** | Noise Tolerance | S&P (~10%), Gaussian ($\sigma \le 20$) | **Median 3×3 + Top-Hat suppresses noise floor entirely** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R19** | Atmospheric Disturbance Resilience | Haze, Fog, Rain, Low-light, Drift | **Aspect-ratio filtering + CNN rejects streaks & distractors** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R22** | Real-Time Frame Processing Speed | $\ge 20$ FPS ($\le 50$ ms/frame) | **Nominal: 63.7 FPS • Max Stress: 21.8 FPS • Pure Engine: 154 FPS** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |

---

## 🏗️ 3. System Architecture & Modular Layout

```
fsoc_tracker/ (Repository Root)
├── web/                                 # 3D Mission Control HUD (React 19, Three.js, Vite)
│   ├── src/                             # 3D Earth, Space Scene, Radar, HUD Overlays, Video Bench
│   │   ├── hud/Drawers.tsx              # Contextual Drawers & Algorithm Plugin Playground UI
│   │   ├── services/providers.ts        # WebSocket Remote Engine Provider with Auto-Reconnect
│   │   └── state/store.ts               # Reactive Zustand Store with <25ms Low-Latency HUD Loop
│   ├── public/                          # Static assets and benchmark datasets
│   └── package.json
│
├── fsoc_engine/                         # Core Python Tracking & AI Perception Engine
│   ├── src/fsoc/
│   │   ├── core/                        # Types, Config (Pydantic), Camera Kinematics, Engine
│   │   ├── simulation/                  # Ground-truth 2000x2000 scene & 7 motion models
│   │   ├── disturbances/                # Noise, Jitter, Drift, Fog, Haze, Rain streaks
│   │   ├── vision/                      # SpotDetector, Optical Flow, CNN Verifier
│   │   ├── tracking/                    # IMM Multi-Model Filter, Particle Filter, State Machine
│   │   ├── control/                     # PID Controller + Anti-Windup + Feed-Forward Slew
│   │   ├── plugins/                     # ⚡ Custom Algorithm Plugin Architecture
│   │   │   ├── registry.py              # Hot-reloadable Plugin Registry & Function Dispatcher
│   │   │   ├── contracts.py             # Strict Function Contracts, Signatures & Defaults
│   │   │   ├── presets.py               # Pre-Tuned Presets (RL Cascaded PID, Kalman, PSF, etc.)
│   │   │   └── ab_runner.py             # Automated Comparative A/B Performance Testing Suite
│   │   ├── benchmarks/                  # Benchmark-1 & Benchmark-2 Automated Evaluators
│   │   ├── gui/                         # Desktop Tkinter GUI Workstation & Plugin Panel
│   │   └── server/app.py                # FastAPI Telemetry Streaming & Plugin REST Endpoints
│   ├── configs/                         # YAML System & Disturbance Configurations
│   ├── models/                          # ONNX Trained Beacon Verification Models
│   ├── test_videos/                     # Multi-Tier Ground-Truth CSV Datasets
│   ├── tests/                           # 208 Unit and Integration Tests
│   └── pyproject.toml / requirements.txt
│
├── test_videos/                         # Root Multi-Tier Ground-Truth CSV Datasets
├── main.py                              # Universal Root CLI Launcher
├── build_exe.py                         # Standalone PyInstaller Executable Builder
├── run_demo.bat                         # 1-Click Desktop GUI Launcher
├── run_benchmarks.bat                   # 1-Click Automated Benchmark Runner
├── start_servers.bat                    # 1-Click Full Stack Launcher (FastAPI + React)
└── start_3d_web.bat                     # 1-Click 3D Mission Control Web Launcher
```

---

## ⚡ 4. Custom Algorithm Plugin Architecture & Live Playground

NETRA features an advanced, research-grade **Plugin Architecture** that allows algorithm developers and researchers to hot-swap or inject proprietary algorithms into the core tracking engine in real time without restarting the application.

### Pipeline Slots & Function Contracts

The architecture supports three primary processing stages:

```
           ┌────────────────┐       ┌─────────────────┐       ┌─────────────────┐
Raw Frames │  VISION SLOT   │ Spot  │  TRACKING SLOT  │ State │  CONTROL SLOT   │ Motor
──────────►│ (Centroiding)  ├──────►│ (Filtering/IMM) ├──────►│ (Servo/PID Loop) ├──────► Rates
           └────────────────┘       └─────────────────┘       └─────────────────┘
```

1. **`control` Slot — Servo Control Loop**:
   - **Contract**: `def control(error, velocity, dt, state, ctx, params) -> {"pan_rate": float, "tilt_rate": float}`
   - **Inputs**: Boresight pixel error `(e_x, e_y)`, target velocity `(vx, vy)`, timestep `dt`, persistent state dictionary `state`, context `ctx` (containing `px_per_deg_x/y`, `pan/tilt_deg`), and tunable `params`.
   - **Outputs**: Gimbal motor rate commands in deg/s.

2. **`tracking` Slot — State Estimation & Trajectory Filtering**:
   - **Contract**: `def track(measurement, dt, state, ctx, params) -> {"x": float, "y": float, "vx": float, "vy": float, "cov": float, "state": str}`
   - **Inputs**: Raw vision measurement `{"x", "y", "confidence"}` (or `None` during deep fades/cloud occlusions), timestep `dt`, state dictionary, and `params`.
   - **Outputs**: Filtered target coordinates, velocity estimates, and tracking state.

3. **`vision` Slot — Sub-Pixel Centroid Detection**:
   - **Contract**: `def detect(image, prev_state, ctx, params) -> {"x": float, "y": float, "intensity": float, "confidence": float} | None`
   - **Inputs**: 2D grayscale uint8 sensor frame, prior tracking state, optical context, and `params`.
   - **Outputs**: Centroid coordinate detection with confidence score or `None` if obscured.

### Key Architectural Capabilities

- **Zero-Downtime Hot-Reloading**: Algorithms can be pasted and applied on the fly via the 3D Web HUD or Desktop GUI.
- **Fail-Safe Automatic Fallback**: If user-injected Python code raises a runtime exception or syntax error, the engine automatically catches it and transparently falls back to the high-performance NETRA default (IMM Kalman Filter + Cascaded PID) without dropping a frame.
- **Dynamic AST Parameter Discovery**: When custom code references `params.get("ParamName", default_value)`, the system parses the Abstract Syntax Tree (AST) and automatically generates interactive, real-time sliders in the UI.
- **Pre-Tuned Research Baseline Presets**:
  - *Control*: Reinforcement-Learning DDPG Tuned Cascaded PID (arXiv:2607.15910), Damped Classical PD, Phase Lead-Lag.
  - *Tracking*: Alpha-Beta ($\alpha$-$\beta$) Tracking Filter, Single Extended Kalman Filter, Exponential Moving Average (EMA).
  - *Vision*: Normalized Gaussian PSF Matching, Brightest Blob Centroiding.
- **Comparative A/B Verification Reports**: Run side-by-side Monte Carlo benchmarking between the active plugin and the default NETRA baseline to evaluate Delta RMSE %, Lock Retention %, FPS throughput, and formal R14 compliance verdicts with one-click printable HTML/JSON exports.

---

## 🚀 5. Quickstart Guide

### Option A: 1-Click Launchers (Windows)
- **Full Stack (FastAPI Backend + React Frontend)**: Double-click [`start_servers.bat`](start_servers.bat)
- **3D Web Mission Control**: Double-click [`start_3d_web.bat`](start_3d_web.bat) (Opens http://localhost:5173)
- **Desktop GUI Telemetry Workstation**: Double-click [`run_demo.bat`](run_demo.bat)
- **Run Automated Benchmarks**: Double-click [`run_benchmarks.bat`](run_benchmarks.bat)
- **Standalone Windows Executable**: Double-click [`run_exe.bat`](run_exe.bat)

### Option B: Command-Line Interface (CLI)

```bash
# 1. Run Complete Automated Benchmark Suite (Benchmark-1 & Benchmark-2):
python main.py benchmark --type all --duration 2.0

# 2. Run Benchmark-1 across 10 simulation scenarios:
python main.py benchmark --type 1 --duration 3.0

# 3. Launch Native Desktop Operator Workstation with Plugin Panel:
python main.py gui

# 4. Run Single Closed-Loop Simulation with Custom YAML:
python main.py run --config fsoc_engine/configs/default.yaml --duration 5.0
```

---

## 📹 6. Multi-Tier Ground-Truth Benchmark Datasets

Under [`test_videos/`](test_videos/) and [`fsoc_engine/test_videos/`](fsoc_engine/test_videos/), the system includes high-precision 60 FPS ground-truth CSV datasets covering extreme operational conditions:

| Dataset | Ground-Truth File | Environmental Conditions | Verification Focus |
| :--- | :--- | :--- | :--- |
| **Clear Sky** | `01_clear_sky_decoy_10s_gt.csv` | Clear Atmosphere • Single Decoy | Baseline trajectory accuracy & sub-pixel convergence |
| **Haze** | `02_haze_moving_glint_10s_gt.csv` | Moving Glint • Reduced Contrast | Slew rate tracking & PID damping |
| **Dense Fog** | `03_dense_fog_glint_10s_gt.csv` | Dense Fog • Flickering Glint | IMM model switching between CV and CT |
| **Rain Streaks** | `04_rain_streaks_decoys_10s_gt.csv` | Rain Streaks • Multiple Decoys | False-positive rejection & optical flow gating |
| **Turbulence** | `05_hard_turbulence_deep_fade_10s_gt.csv`| Severe Turbulence • Deep Fades | Particle Filter re-acquisition during total loss of signal |

> **Note**: Test video MP4 files can be synthesized on demand at 60 FPS using [`fsoc_engine/generate_decoy_benchmark_videos.py`](fsoc_engine/generate_decoy_benchmark_videos.py) or analyzed directly through the Video Benchmark tool in the web interface.

---

## 🧪 7. Testing & Quality Assurance

The codebase includes **208 automated unit and integration tests** with 100% pass rate:

```bash
cd fsoc_engine
pytest tests/unit -v
```

Test coverage encompasses:
- Custom algorithm plugin registry, safe evaluation, exception fallback, and AST parameter parsing (`test_plugins.py`).
- Automated A/B comparative report runner and metrics evaluation (`test_ab_runner.py`).
- Virtual camera kinematics, pan/tilt slew clipping, and latency propagation (`test_camera.py`).
- Noise modeling (Gaussian, Poisson, Salt & Pepper) and atmospheric scattering (`test_disturbances.py`).
- Sub-pixel centroid accuracy (< 0.2 px clean, < 2.5 px under heavy noise) (`test_vision.py`).
- Wide-area acquisition speed (< 50 ms scan, $\le 0.53$ s total slew).
- ONNX CNN verifier false-positive discrimination.
- IMM multi-model probability transitions and particle filter re-acquisition (`test_imm.py`, `test_particle_filter.py`).
- PID closed-loop control and feed-forward compensation (`test_tracking_control.py`).
- Automated benchmark execution and compliance reporting (`test_benchmarks.py`).

---

## 📦 8. Building the Standalone Windows Release

NETRA includes an automated, one-command release build pipeline producing a standalone PyInstaller onedir distribution, Inno Setup wizard installer, and portable ZIP.

### Prerequisites (Windows Build System)
- **Python 3.11 or 3.12 (x64)**
- **PyInstaller**: `pip install pyinstaller`
- **Inno Setup 6.3+**: [Download Inno Setup](https://jrsoftware.org/isdl.php) (adds `ISCC.exe` to PATH or Program Files)

### One-Command Release Build
From the `fsoc_engine/` directory on a Windows machine:
```bat
build_release.bat
```

This single command automatically:
1. Generates multi-size Windows icon (`assets/netra.ico`), branded startup splash (`assets/splash.png`), and Inno Setup artwork (`wizard_side.bmp`, `wizard_small.bmp`).
2. Freezes the application with PyInstaller using [`NETRA.spec`](fsoc_engine/NETRA.spec) into `dist/NETRA/`.
3. Creates the standalone portable archive [`release/NETRA-Portable.zip`](fsoc_engine/release/NETRA-Portable.zip).
4. Compiles the modern Inno Setup installer wizard [`release/NETRA-Setup.exe`](fsoc_engine/release/NETRA-Setup.exe).
5. Computes SHA-256 release integrity hashes into [`release/checksums.txt`](fsoc_engine/release/checksums.txt).

### Standalone Build Verification (Smoke Test)
Verify the frozen build without launching the GUI:
```bat
dist\NETRA\NETRA.exe --selftest
```
Exits with returncode `0` on PASS and saves an auto-generated compliance performance report to `%APPDATA%\NETRA\reports\`.

