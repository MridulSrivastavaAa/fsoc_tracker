# NETRA: AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals

> **ISRO / SAC Problem Statement 26169 • Smart India Hackathon (SIH)**  
> **System Designation:** **NETRA** (Networked Electro-optical Tracking & Rapid Alignment)  
> **Status:** 100% Complete • 198+ Unit & Integration Tests Passing • Zero Failures • Production-Ready

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
5. **Interactive 3D Web Mission Control & HUD (`web/`)**: High-performance Three.js + React 19 visualizer featuring Earth orbit trajectory, tactical reticles, live telemetry stream, and Benchmark-2 video player with interactive trajectory playback.
6. **Standalone Desktop Application**: Precompiled native executable (`FSOCTracker.exe`) bundled with all models, configs, and offline web runtime.

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
│   ├── public/                          # Static assets and test video feeds
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
│   │   ├── benchmarks/                  # Benchmark-1 & Benchmark-2 Automated Runners
│   │   ├── gui/                         # Desktop GUI Workstation & PyWebView App
│   │   └── server/                      # FastAPI Backend for Web Telemetry Streaming
│   ├── configs/                         # YAML System & Disturbance Configurations
│   ├── models/                          # ONNX Trained Beacon Verification Models
│   ├── test_videos/                     # 5-Tier Synthetic Test Videos & Ground-Truth CSVs
│   ├── dist/FSOCTracker/                # Standalone Native Executable (FSOCTracker.exe)
│   ├── tests/                           # 198 Unit and Integration Tests
│   └── pyproject.toml / requirements.txt
│
├── main.py                              # Universal Root CLI Launcher
├── build_exe.py                         # Standalone PyInstaller Executable Builder
├── run_demo.bat                         # 1-Click Desktop GUI Launcher
├── run_benchmarks.bat                   # 1-Click Automated Benchmark Runner
└── start_3d_web.bat                     # 1-Click 3D Mission Control Web Launcher
```

---

## 🚀 4. Quickstart Guide

### Option A: 1-Click Launchers (Windows)
- **3D Web Mission Control**: Double-click [`start_3d_web.bat`](start_3d_web.bat) (Opens http://localhost:5173)
- **Desktop GUI Telemetry Workstation**: Double-click [`run_demo.bat`](run_demo.bat)
- **Run Automated Benchmarks**: Double-click [`run_benchmarks.bat`](run_benchmarks.bat)
- **Run Standalone Executable**: Double-click [`fsoc_engine/dist/FSOCTracker/FSOCTracker.exe`](fsoc_engine/dist/FSOCTracker/FSOCTracker.exe)

### Option B: Command-Line Interface (CLI)

```bash
# 1. Run Complete Automated Benchmark Suite (Benchmark-1 & Benchmark-2):
python main.py benchmark --type all --duration 2.0

# 2. Run Benchmark-1 across 10 simulation scenarios:
python main.py benchmark --type 1 --duration 3.0

# 3. Run Benchmark-2 on Video File with Ground-Truth Comparison:
python main.py benchmark --type 2 --video fsoc_engine/test_videos/tier1_clean_90pct.mp4

# 4. Launch Native Desktop Operator Workstation:
python main.py gui

# 5. Run Single Closed-Loop Simulation with Custom YAML:
python main.py run --config fsoc_engine/configs/default.yaml --duration 5.0
```

---

## 📹 5. Multi-Tier Benchmark Test Suite

Under [`fsoc_engine/test_videos/`](fsoc_engine/test_videos/), the system includes 5 multi-tier synthetic evaluation videos with corresponding ground-truth CSVs:

| Tier | Dataset File | Environmental Conditions | Verification Focus |
| :--- | :--- | :--- | :--- |
| **Tier 1** | `tier1_clean_90pct.mp4` | 90% Clean • Pure Sky • High SNR | Baseline trajectory accuracy & sub-pixel convergence |
| **Tier 2** | `tier2_mild_70pct.mp4` | 70% Clarity • Light Haze • Minor Vibration | Slew rate tracking & PID damping |
| **Tier 3** | `tier3_moderate_50pct.mp4` | 50% Clarity • Moderate Fog • Scintillation | IMM model switching between CV and CT |
| **Tier 4** | `tier4_degraded_30pct.mp4` | 30% Clarity • Rain Streaks • Platform Drift | False-positive rejection & optical flow gating |
| **Tier 5** | `tier5_extreme_10pct.mp4` | 10% Visibility • Heavy Jitter & Dropouts | Particle Filter re-acquisition during total loss of signal |

---

## 🧪 6. Testing & Quality Assurance

The codebase includes **198 automated unit and integration tests** with 100% pass rate:

```bash
cd fsoc_engine
pytest tests/ -v
```

Test coverage encompasses:
- Virtual camera kinematics, pan/tilt slew clipping, and latency propagation.
- Noise modeling (Gaussian, Poisson, Salt & Pepper) and atmospheric scattering.
- Sub-pixel centroid accuracy (< 0.2 px clean, < 2.5 px under heavy noise).
- Wide-area acquisition speed (< 50 ms scan, <= 0.53 s total slew).
- ONNX CNN verifier false-positive discrimination.
- IMM multi-model probability transitions and particle filter re-acquisition.
- PID closed-loop control and feed-forward compensation.
- Automated benchmark execution and JSON/CSV reporting.
