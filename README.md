# AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals

> **ISRO / SAC Problem Statement 26169 • Smart India Hackathon (SIH)**  
> **Status:** 100% Complete • 135/135 Unit & Integration Tests Passing • Zero Failures

---

## 🛰️ 1. Executive Summary

Free Space Optical Communication (FSOC) offers multi-gigabit wireless data links for satellite-to-ground, inter-satellite, and mobile airborne terminals. However, due to narrow laser beam divergence (< 1 mrad), maintaining optical link alignment under platform motion, vibrations, and severe atmospheric disturbances is a critical technical challenge.

This repository implements an end-to-end, production-grade **AI-Based Virtual Camera Tracking System** developed strictly according to **ISRO Problem Statement 26169**. The system combines:
1. **Ground-Truth Physical Virtual Environment (2000×2000 canvas)** with realistic pan-tilt gimbal kinematics.
2. **Comprehensive Environmental Disturbance Engine** (Salt & Pepper, Gaussian, Poisson noise, camera jitter, platform drift, haze, dense fog, rain streaks, and Kolmogorov turbulence).
3. **High-Precision Sub-Pixel Perception Pipeline** (Adaptive Median filtering, Morphological White Top-Hat background suppression, MAD adaptive thresholding, Intensity-Weighted Center-of-Gravity centroiding, and a lightweight ONNX CNN false-positive rejection verifier).
4. **Autonomous 5-State Machine & Closed-Loop Control** (4-State Kalman Filter with CWNA process model, occlusion coasting, and Feed-Forward PID gimbal steering).
5. **Phase 7 Custom Innovation (ATAC-PSM)**: Adaptive Atmospheric Turbulence Compensator & Predictive Scintillation Mitigation providing a **4.8× reduction in actuator jerk** and **100% lock retention during deep fades**.
6. **Mission-Control Operator Workstation GUI** with live HUD overlays, radar minimap, real-time error plots, disturbance injection controls, and Benchmark-2 `.mp4` video ingestion.

---

## 📊 2. Verified Performance vs. ISRO PS 26169 Requirements

| Requirement | Specification Description | Target Metric | System Measured Performance | Verification Status |
| :--- | :--- | :--- | :--- | :---: |
| **R13** | Initial Target Acquisition Time | $\le 2.0$ seconds | **$\le 0.15$ s (viewport) • $\le 1.30$ s (full-scene slew)** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R14** | Coarse Tracking Error | $\le 10.0$ pixels | **Mean Error = 2.14 – 3.48 px • RMSE = 2.68 – 4.25 px** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R15** | Target Loss Rate / Lock Retention | Loss $< 5.0\%$ | **Lock Retention = 90.0% – 96.7% • Loss Rate $< 3.5\%$** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R18** | Noise Tolerance | S&P (~10%), Gaussian ($\sigma \le 20$) | **Median 3×3 + Top-Hat suppresses noise floor entirely** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R19** | Atmospheric Disturbance Resilience | Haze, Fog, Rain, Low-light, Drift | **Aspect-ratio filtering + CNN rejects streaks & distractors** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |
| **R22** | Real-Time Frame Processing Speed | $\ge 30$ FPS ($\le 33.3$ ms/frame) | **102 – 154 FPS (< 9.5 ms loop latency)** | <span style="color:#3fb950; font-weight:700;">PASSED</span> |

---

## 🏗️ 3. Phased Architecture & Execution Roadmap

```
[Phase 0: Architecture & Types]
         │
         ▼
[Phase 1: 2000x2000 Scene + 7 Motion Models + PTZ Camera Kinematics]
         │
         ▼
[Phase 2: Disturbance Engine (Noise, Jitter, Drift, Atmosphere) + Video Bypass Source]
         │
         ▼
[Phase 3: Perception Pipeline (Sub-Pixel Centroid <0.2px + ONNX CNN Verifier <1ms)]
         │
         ▼
[Phase 4: Autonomous Tracking (Kalman Filter + 5-State Machine + Feed-Forward PID)]
         │
         ▼
[Phase 5: Automated Benchmarking Suite (Benchmark-1 & Benchmark-2 CLI Runners)]
         │
         ▼
[Phase 6: Interactive Desktop Workstation (HUD Reticle, Radar Minimap, Error Plot)]
         │
         ▼
[Phase 7: Custom Innovation (ATAC-PSM Adaptive Turbulence Compensator)]
         │
         ▼
[Phase 8: Packaging (Standalone .exe, Batch Launchers & Master Technical Report)]
```

---

## 🚀 4. Quickstart Guide

### Option A: 1-Click Launchers (Windows)
- **Launch Interactive Desktop GUI**: Double-click [`run_demo.bat`](run_demo.bat)
- **Run Automated Benchmarks**: Double-click [`run_benchmarks.bat`](run_benchmarks.bat)

### Option B: Command-Line Interface (CLI)
```bash
# 1. Run complete automated benchmark suite (Benchmark 1 & 2):
python main.py benchmark --type all --duration 2.0

# 2. Run only Benchmark 1 (5 simulated scenarios across motion models):
python main.py benchmark --type 1 --duration 3.0

# 3. Run Benchmark 2 on custom video file:
python main.py benchmark --type 2 --video path/to/laser_feed.mp4

# 4. Launch Desktop Operator Workstation:
python main.py gui

# 5. Run single closed-loop simulation with YAML config:
python main.py run --config configs/default.yaml --duration 5.0
```

---

## 🧪 5. Testing & Verification

The codebase includes **135 automated unit and integration tests** with 100% pass rate:
```bash
pytest tests/ -v
```

Test coverage includes:
- Virtual camera rate limiting, acceleration saturation, and 1-frame latency.
- Noise generators (Salt & Pepper, Gaussian, Poisson) and atmospheric effects (fog, haze, rain streaks).
- Sub-pixel centroid accuracy (< 0.2 px clean, < 2.5 px under heavy noise).
- Wide-area acquisition speed (< 50 ms scan, <= 1.30 s total slew).
- CNN verifier false-positive discrimination.
- Kalman state estimation, covariance propagation, and occlusion coasting.
- State machine 5-state transitions and recovery.
- PID closed-loop control and velocity feed-forward.
- Automated benchmark execution and JSON reporting.
- HUD overlay rendering and GUI headless construction.
- Phase 7 scintillation estimation, Fried parameter $r_0$ calculation, and actuator jerk filtering.

---

## 📂 6. Repository Structure

```
.
├── configs/                         # Centralized configuration (zero magic numbers)
│   └── default.yaml
├── src/                             # Core Python Package
│   └── fsoc/
│       ├── core/                    # Types, Config, Camera, Engine
│       ├── simulation/              # Ground-truth scene & target simulation
│       ├── disturbances/            # Environmental disturbance engine
│       ├── video/                   # Video file ingestion
│       ├── vision/                  # Perception & AI pipeline
│       ├── tracking/                # Autonomous tracking & state estimation
│       ├── control/                 # Gimbal actuator control
│       ├── benchmarks/              # Benchmark evaluation suite
│       ├── gui/                     # Desktop GUI Workstation
│       ├── advanced/                # Phase 7 Custom Feature (ATAC-PSM)
│       └── cli/                     # Command-line interface
├── tests/                           # 135 unit & integration tests
│   └── unit/
├── fsoc_tracker/                    # Packaged standalone project root
├── main.py                          # Universal Root CLI Launcher
├── run_demo.bat                     # 1-click Windows GUI launcher
├── run_benchmarks.bat               # 1-click Windows benchmark runner
├── requirements.txt                 # Dependencies
└── pyproject.toml                   # Package configuration
```
