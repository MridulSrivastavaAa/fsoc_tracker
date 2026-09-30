# NETRA Engine: Core Python Tracking & AI Perception Pipeline

> **ISRO / SAC Problem Statement 26169 • Smart India Hackathon (SIH)**  
> **Package:** `fsoc_engine` (Python 3.10+ / PyTorch / ONNX Runtime / OpenCV / NumPy / SciPy)  
> **Status:** 100% Complete • 198 Unit & Integration Tests Passing • Zero Failures

---

## 🛰️ 1. Overview

`fsoc_engine` contains the physical simulation engine, perception pipeline, multi-model state estimation, and gimbal motion controllers for the **NETRA** FSOC coarse tracking system.

Key subsystems:
1. **Simulation (`src/fsoc/simulation/`)**: 2000×2000 continuous ground-truth physical canvas, target radiometry, 7 motion models.
2. **Disturbances (`src/fsoc/disturbances/`)**: Parametric atmospheric scattering, Kolmogorov turbulence, Gaussian/Poisson/S&P noise, and 2-axis platform jitter.
3. **Perception (`src/fsoc/vision/`)**: Sub-pixel intensity-weighted centroiding, morphological background removal, adaptive optical flow gating, and ONNX-runtime CNN verification.
4. **Estimation & Recovery (`src/fsoc/tracking/`)**: Interacting Multiple Model (IMM) filter (CV + CT + RW) and multi-particle re-acquisition filter.
5. **Control (`src/fsoc/control/`)**: 2-axis pan/tilt PID controller with anti-windup and rate-limited kinematic slew.
6. **Benchmarks (`src/fsoc/benchmarks/`)**: Automated evaluation suite producing compliant JSON, CSV, and markdown summaries.

---

## 🚀 2. Usage & CLI Execution

Run commands directly from this folder or through the root `main.py` launcher:

```bash
# 1. Run Complete Benchmark Suite (Benchmark 1 & 2):
python main.py benchmark --type all --duration 2.0

# 2. Run Benchmark 1 (Simulated Scenarios):
python main.py benchmark --type 1 --duration 3.0

# 3. Run Benchmark 2 (Video Benchmark on Multi-Tier Test Videos):
python main.py benchmark --type 2 --video test_videos/tier1_clean_90pct.mp4

# 4. Launch Native Desktop Workstation GUI:
python main.py gui

# 5. Run Single Closed-Loop Simulation:
python main.py run --config configs/default.yaml --duration 5.0
```

---

## 🧪 3. Running Unit Tests

```bash
pytest tests/ -v
```

All 198 unit tests evaluate:
- Camera projection and rate limits (`test_camera.py`)
- Disturbance injection and noise statistics (`test_disturbances.py`)
- Vision, morphology, and CNN candidate verifiers (`test_vision.py`)
- Optical flow gating confidence (`test_flow_gating.py`)
- IMM filter model switching & covariance bounds (`test_imm.py`, `test_imm_trajectories.py`)
- Particle filter re-acquisition latency (`test_particle_filter.py`)
- Closed-loop PID stability and settling time (`test_tracking_control.py`)
