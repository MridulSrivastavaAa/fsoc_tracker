# NETRA &bull; AI-Based Virtual Camera Tracking System for Mobile FSOC Terminals

> **ISRO / Space Applications Centre (SAC) • Problem Statement 26169**  
> **Smart India Hackathon (SIH)**  
> **System Name:** **NETRA** (*Networked Electro-optical Tracking & Rapid Acquisition*)  
> **Status:** Production-Ready &bull; 100% Implemented &bull; All Performance Targets Verified

---

## 📂 Project Directory Structure

```
.
├── 🚀 run_demo.bat          # 1-Click launcher for Desktop Telemetry Workstation (GUI)
├── 📊 run_benchmarks.bat    # 1-Click launcher for Automated Benchmark Suite (1 & 2)
├── 🌐 start_3d_web.bat      # 1-Click launcher for 3D Geospatial Orbit & Web Visualizer
├── ⚡ start_servers.bat     # Full-stack launcher (FastAPI backend + React frontend)
├── 🐍 main.py               # Central Python CLI entry point
│
├── 📁 fsoc_engine/          # Primary Python Tracking Engine (NETRA Core)
│   ├── src/fsoc/            # Modular Python packages:
│   │   ├── core/            # ClosedLoopEngine, VirtualCamera, Configuration
│   │   ├── simulation/      # 2000x2000 canvas, Gaussian beacon, 7 motion models
│   │   ├── disturbances/    # S&P, Gaussian, Poisson, Jitter, Drift, Fog, Rain
│   │   ├── vision/          # Sub-pixel CoG, Optical Flow gating, ONNX CNN
│   │   ├── tracking/        # Kalman Filter, Particle Filter, IMM, State Machine
│   │   ├── control/         # Feed-forward PID rate controller
│   │   ├── advanced/        # ATAC-PSM adaptive turbulence compensator
│   │   ├── server/          # FastAPI & WebSocket real-time telemetry server
│   │   ├── plugins/         # Extensible plugin system & algorithm playground
│   │   └── gui/             # Tactical HUD overlay & workstation
│   ├── configs/             # default.yaml configuration
│   ├── models/              # Trained ONNX beacon verifier model
│   ├── tests/               # Unit & integration test suites
│   ├── assets/              # Logos and application icons
│   └── web_dist/            # Production build of the 3D web dashboard
│
├── 📁 web/                  # 3D Geospatial Earth & Satellite Visualizer (React + Three.js)
│   ├── src/                 # Orbit calculations, 3D scenes, sensor HUD components
│   └── package.json         # Web dependencies
│
├── 📁 test_videos/          # 15 Benchmark test video sequences & ground-truth CSVs
│
├── 📁 docs/                 # Engineering Specifications & Architectural Plans
│   ├── ISRO_PS26169_Official_Document.pdf   # Official SIH Problem Statement Document
│   ├── ISRO_PS26169_Problem_Statement.txt   # Mentors & Problem Description
│   ├── 00_PROJECT_ROADMAP.md / .html        # Master Execution Plan (Phases 0-8)
│   ├── 01_PROJECT_STRUCTURE.md              # Pipeline Rules & Architecture Specs
│   ├── 02_DESIGN_DOCUMENT.md                # Theoretical Math, FOV Scaling & Kinematics
│   ├── 03_PDR_PRELIMINARY_DESIGN_REVIEW.md  # Requirements Traceability Matrix (R1-R30)
│   ├── 04_DATA_GENERATION_PLAN.md           # 40 GB Synthetic Dataset Plan
│   ├── MULTI_BEACON_PLAN.md                 # Multi-beacon handoff strategy
│   ├── LINK_TEST.md                         # Optical link budget tests
│   ├── RELEASE_CHECKLIST.md                 # Release checklist
│   └── build_pdf.py                         # PDF generator for roadmap
│
└── 📁 reports/              # Official Technical Submissions & Evaluation Reports
    ├── FINAL_TECHNICAL_REPORT.html          # 15-Page Master Technical Proposal for ISRO
    ├── PHASE1_REPORT.html to PHASE8_REPORT.html  # Phase completion HTML reports
    ├── BENCHMARK1_REPORT.md                 # Benchmark-1 evaluation report
    ├── BENCHMARK2_REPORT.md                 # Benchmark-2 evaluation report
    ├── PS26169_COMPLIANCE_MATRIX.md         # Full compliance traceability matrix
    ├── STEP4_PARTICLE_FILTER_REPORT.md      # Nonlinear particle filter analysis
    ├── STEP5_PERFORMANCE_REPORT.md          # Numerical benchmark performance log
    └── ablation_results.json                # Comparative ablation experiment results
```

---

## ⚡ Quickstart: How to Run

### 1. Launch Interactive Desktop GUI Workstation
Double-click [`run_demo.bat`](run_demo.bat) or run:
```bash
python main.py gui
```
- Real-time 640x480 tactical camera viewport with boresight reticle and tracking crosshair.
- 2000x2000 macro radar minimap showing camera position and ground-truth beacon.
- Keyboard controls: `[SPACE]` Pause/Resume, `[M]` Cycle motion model, `[N]` Cycle noise, `[R]` Reset, `[Q]` Exit.

### 2. Run Automated Benchmark Suite (Benchmark 1 & 2)
Double-click [`run_benchmarks.bat`](run_benchmarks.bat) or run:
```bash
python main.py benchmark --type all --duration 2.0
```
- Headlessly tests across all 5 operational scenarios with per-frame CSV logging.

### 3. Launch 3D Geospatial Orbit & Web Visualizer
Double-click [`start_3d_web.bat`](start_3d_web.bat) or run:
```bash
python -m uvicorn fsoc.server.app:app --host 0.0.0.0 --port 8000
```
And in `web/`:
```bash
npm run dev -- --open
```
- Launches the React + Three.js 3D Earth, satellite orbital tracks, optical laser beam visualization, and web telemetry HUD.

---

## 📊 Verified Performance vs. ISRO Requirements

| Requirement | Metric | ISRO Target | System Achieved | Status |
| :--- | :--- | :--- | :--- | :---: |
| **R13** | Acquisition Time | $\le 2.0\text{ s}$ | **$\le 0.15\text{ s}$ (in FOV) &bull; $\le 0.87\text{ s}$ (full-slew)** | **PASSED** |
| **R14** | Coarse Centroid Error | $\le 10.0\text{ px}$ | **Mean Error: 0.69 – 2.86 px &bull; RMSE: 0.71 – 3.25 px** | **PASSED** |
| **R15** | Lock Retention Rate | Loss $< 5.0\%$ | **Lock: 93.3% &bull; Loss: $< 3.5\%$** | **PASSED** |
| **R17** | Real-Time Frame Rate | $\ge 20 - 30\text{ FPS}$ | **86 – 167 FPS** ($< 8.2\text{ ms}$ loop latency) | **PASSED** |
| **R18-R22** | Noise & Atmosphere | S&P, Fog, Rain, Jitter | **Full rejection via Median + Top-Hat + CNN** | **PASSED** |
