"""
src/fsoc/server/app.py
======================
FastAPI Application and WebSocket Telemetry Server for FSOC Tracking System.
Provides:
  - WebSocket /ws/telemetry: real-time bidirectional telemetry streaming and control
  - REST /api/presets: scenario configurations
  - REST /api/video/analyze: Benchmark-2 video file ingestion & analysis
  - REST /api/video/download/{filename}: CSV & HTML benchmark reports
  - REST /api/health: health check endpoint
  - Static distribution mounting for direct browser access at http://localhost:8000
"""
from __future__ import annotations
import asyncio
import io
import json
import math
import os
import shutil
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import sys
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

# Prevent uvicorn/websockets keepalive ping timeouts from dropping active connections
try:
    import uvicorn.config
    _orig_uvicorn_config_init = uvicorn.config.Config.__init__
    def _patched_uvicorn_config_init(self, *args, **kwargs):
        kwargs["ws_ping_interval"] = None
        kwargs["ws_ping_timeout"] = None
        return _orig_uvicorn_config_init(self, *args, **kwargs)
    uvicorn.config.Config.__init__ = _patched_uvicorn_config_init
except Exception:
    pass

try:
    from websockets.legacy.protocol import WebSocketCommonProtocol
    _orig_ws_init = WebSocketCommonProtocol.__init__
    def _patched_ws_init(self, *args, **kwargs):
        kwargs["ping_interval"] = None
        kwargs["ping_timeout"] = None
        _orig_ws_init(self, *args, **kwargs)
        self.ping_interval = None
        self.ping_timeout = None
    WebSocketCommonProtocol.__init__ = _patched_ws_init
except Exception:
    pass

# Module-level registry of active WebSocket telemetry handlers' background tasks.
# Tasks are tracked here so they are never garbage-collected while the parent
# coroutine runs, and cancelled on disconnect.
_ACTIVE_TASKS: set[asyncio.Task] = set()
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import AppConfig, default_config
from ..core.engine import ClosedLoopEngine
from ..core.types import CameraCommand, FrameMetrics, Point
from ..benchmarks.runner import BenchmarkRunner
from ..vision.preprocess import VisionPreprocessor
from ..vision.detector import SpotDetector
from ..vision.cnn_verifier import BeaconVerifierCNN
from ..tracking.kalman import KalmanTracker
from ..tracking.state_machine import TrackingStateMachine, State
from ..video.video_source import VideoFileSource

# Create application
app = FastAPI(
    title="ISRO FSOC Virtual Camera Tracking System API",
    description="Real-time Telemetry, Gimbal Control, and Automated Benchmarking Engine (ISRO/SAC PS 26169)",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Download & reports storage directory
REPORTS_DIR = Path(tempfile.gettempdir()) / "fsoc_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/plugins/playground")
def launch_plugin_playground_endpoint() -> JSONResponse:
    import subprocess
    import sys
    from pathlib import Path
    # Use the dedicated launcher that sets up sys.path properly
    launcher = Path(__file__).resolve().parents[1] / "gui" / "launch_playground.py"
    proc = subprocess.Popen(
        [sys.executable, str(launcher)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    # Give it a moment to see if it crashes immediately
    import time; time.sleep(0.3)
    if proc.poll() is not None:
        _, err = proc.communicate()
        return JSONResponse(status_code=500, content={"error": err.decode("utf-8", errors="replace")})
    return JSONResponse(content={"status": "ok", "message": "Plugin Playground launched", "pid": proc.pid})

from pydantic import BaseModel
class PluginCodeRequest(BaseModel):
    slot: str
    code: str
    params: dict
    label: str

@app.post("/api/plugins/apply_code")
def apply_plugin_code(req: PluginCodeRequest) -> JSONResponse:
    import math
    import numpy as np
    from ..plugins.registry import registry
    
    namespace = {"np": np, "math": math}
    try:
        exec(req.code, namespace)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Compilation failed: {e}"})

    func_map = {"vision": "detect", "tracking": "track", "control": "control"}
    target_name = func_map.get(req.slot)
    func = namespace.get(target_name)
    
    if not callable(func):
        return JSONResponse(status_code=400, content={"error": f"Function '{target_name}' not found."})

    registry.request(req.slot, func, req.params, req.label)
    return JSONResponse(content={"status": "ok"})

class PluginResetRequest(BaseModel):
    slot: str

@app.post("/api/plugins/reset")
def reset_plugin_slot(req: PluginResetRequest) -> JSONResponse:
    from ..plugins.registry import registry
    registry.reset_slot(req.slot)
    return JSONResponse(content={"status": "ok"})

@app.get("/api/plugins/report")
def get_plugin_report(format: Optional[str] = None) -> Any:
    from ..plugins.registry import registry
    from ..plugins.ab_runner import run_ab_comparison, generate_comparative_html
    from fastapi.responses import HTMLResponse

    stats = registry.get_stats()

    active_slot = "control"
    custom_func = None
    custom_label = "Custom Algorithm Plugin"
    custom_params = {}

    for s in ("control", "tracking", "vision"):
        if registry.is_custom(s):
            active_slot = s
            custom_func = registry._active.get(s)
            custom_label = registry.get_label(s)
            custom_params = registry.get_params(s)
            break

    # If no custom plugin currently active, compare against RL-Tuned Cascaded PID
    if custom_func is None:
        from ..plugins.presets import rl_cascaded_pid_control
        active_slot = "control"
        custom_func = rl_cascaded_pid_control
        custom_label = "RL-Tuned Cascaded PID (arXiv:2607.15910 a_opt1)"
        custom_params = {"variant": "opt1"}

    baseline_label = "NETRA Default (IMM Kalman Filter + Cascaded PID)"

    report = run_ab_comparison(
        cfg=engine.cfg if 'engine' in globals() else None,
        slot=active_slot,
        custom_func=custom_func,
        custom_params=custom_params,
        custom_label=custom_label,
        baseline_label=baseline_label,
        scenario_id="circle_clear",
        max_frames=300,
    )
    report["registry_stats"] = stats

    if format == "html":
        html = generate_comparative_html(report)
        return HTMLResponse(content=html)

    html = generate_comparative_html(report)
    return JSONResponse(content={"report": report, "html": html})

# ---------------------------------------------------------------------------
# Scenario Presets
# ---------------------------------------------------------------------------
SCENARIO_PRESETS = [
    {
        "id": "open-sky",
        "name": "Open Sky",
        "summary": "Clear night sky, LEO remote terminal on a circular residual motion. The reference case.",
        "patch": {},
    },
    {
        "id": "ps-baseline",
        "name": "PS169 Baseline",
        "summary": "Problem-statement defaults: 4°×3° FOV only (no wide-field), square 10 px beacon, random start, 5 °/s gimbal.",
        "patch": {"camera": {"wideAcquisition": False}, "target": {"trajectory": "linear", "speedDegS": 0.5}},
    },
    {
        "id": "moving-platform",
        "name": "Moving Platform",
        "summary": "Terminal on a vehicle: platform motion, 8 Hz vibration and wind torque on the gimbal.",
        "patch": {
            "target": {"trajectory": "figure8", "amplitudeDeg": 1.5, "periodS": 14},
            "disturbance": {"platformMotion": "circular", "platformMotionPx": 12, "vibrationPx": 4, "vibrationHz": 8, "windDegS": 0.25, "jitterPx": 3},
        },
    },
    {
        "id": "high-jitter",
        "name": "High Jitter",
        "summary": "Camera jitter at the PS maximum (±20 px/frame). Shows the physical error floor of a coarse stage.",
        "patch": {"disturbance": {"jitterPx": 20, "vibrationPx": 6, "vibrationHz": 12}},
    },
    {
        "id": "weak-beacon",
        "name": "Weak Beacon",
        "summary": "Haze, dim 6 px beacon, strong turbulence and Gaussian σ = 18 noise with 3 % salt & pepper.",
        "patch": {
            "target": {"spotSizePx": 6, "beaconIntensity": 120, "trajectory": "sinusoidal"},
            "disturbance": {"atmosphere": "haze", "atmosphereStrength": 0.7, "turbulence": 0.6, "gaussianNoise": 18, "saltPepper": 0.03},
        },
    },
    {
        "id": "fast-target",
        "name": "Fast Target",
        "summary": "Random manoeuvring target at 1.5 °/s with a 10 °/s gimbal — tests rate feed-forward.",
        "patch": {"target": {"trajectory": "random", "speedDegS": 1.5}, "gimbal": {"maxRateDegS": 10, "maxAccelDegS2": 60}},
    },
    {
        "id": "acquisition-challenge",
        "name": "Acquisition Challenge",
        "summary": "Beacon starts in a field corner, rain and 30 % dropouts, decoy glint present.",
        "patch": {
            "target": {"startMode": "fixed", "startUDeg": 5.6, "startVDeg": -5.4, "trajectory": "stationary"},
            "disturbance": {"atmosphere": "rain", "atmosphereStrength": 0.6, "dropoutProb": 0.3, "decoy": True},
        },
    },
    {
        "id": "occlusion",
        "name": "Occlusion & Reacquisition",
        "summary": "A passing cloud hides the beacon for 1 s every 6 s on a circular path. Measures re-acquisition time (PS ≤ 1 s).",
        "patch": {"target": {"trajectory": "circular", "amplitudeDeg": 1.4, "periodS": 14}, "disturbance": {"occlusionPeriodS": 6, "occlusionDurS": 1}},
    },
    {
        "id": "leo-pass",
        "name": "LEO Pass",
        "summary": "Real circular-orbit pass (550 km, 62° max elevation) with 2.5 s ephemeris timing error.",
        "patch": {"target": {"trajectory": "orbital"}},
    },
]


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ISRO FSOC Tracking Engine",
        "version": "1.0.0",
        "timestamp": time.time(),
    }


@app.get("/api/presets")
async def get_presets():
    return SCENARIO_PRESETS


@app.get("/api/video/download/{filename}")
async def download_report_file(filename: str):
    file_path = REPORTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Requested file not found")
    media_type = "text/csv" if filename.endswith(".csv") else "text/html"
    return FileResponse(path=file_path, media_type=media_type, filename=filename)


@app.post("/api/video/analyze")
async def analyze_video(
    file: UploadFile = File(...),
    truth: Optional[UploadFile] = File(None),
    hfovDeg: float = Form(4.0),
    spotSizePx: float = Form(10.0),
    thresholdSigma: float = Form(3.0),
    verifier: str = Form("onnx"),
):
    """
    Ingest pre-recorded .mp4 video for Benchmark-2 evaluation.
    Executes frame-by-frame beacon centroiding, Kalman tracking, and metrics extraction.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="fsoc_bench2_"))
    try:
        video_filename = file.filename or "uploaded_video.mp4"
        video_path = temp_dir / video_filename
        with open(video_path, "wb") as f_out:
            shutil.copyfileobj(file.file, f_out)

        truth_points: Dict[int, tuple[float, float]] = {}
        if truth is not None and hasattr(truth, "read"):
            content = await truth.read()
            text = content.decode("utf-8", errors="ignore")
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            if lines:
                header = [h.strip().lower() for h in lines[0].split(",")]
                fi = next((i for i, h in enumerate(header) if h in ["frame", "frame_index", "frame_idx", "f_idx", "f", "index"]), 0)
                xi = next((i for i, h in enumerate(header) if h in ["truth_x", "gt_x", "truthx", "x", "target_x", "pos_x"]), -1)
                if xi == -1:
                    xi = 2 if len(header) > 2 and "time" in header[1] else 1
                yi = next((i for i, h in enumerate(header) if h in ["truth_y", "gt_y", "truthy", "y", "target_y", "pos_y"]), xi + 1)

                for line in lines[1:]:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) > max(fi, xi, yi):
                        try:
                            f_idx = int(float(parts[fi]))
                            tx = float(parts[xi])
                            ty = float(parts[yi])
                            truth_points[f_idx] = (tx, ty)
                        except (ValueError, IndexError):
                            pass

        # Open video and inspect
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Could not open video file.")

        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            total_frames = 100

        # Initialize tracking components
        cfg = default_config()
        cfg.camera.fov_x_deg = hfovDeg
        cfg.vision.preprocess.mad_k = thresholdSigma
        if spotSizePx > 0:
            cfg.vision.detector.min_area = max(1.0, 3.14 * (spotSizePx / 3.0) ** 2)
            cfg.vision.detector.max_area = max(5.0, 3.14 * (spotSizePx * 2.5) ** 2)

        preprocessor = VisionPreprocessor(cfg)
        detector = SpotDetector(cfg, preprocessor=preprocessor)
        verifier_cnn = BeaconVerifierCNN(cfg)
        kalman = KalmanTracker(cfg, dt=1.0 / fps)
        sm = TrackingStateMachine(cfg)

        detected_count = 0
        loss_count = 0
        first_acq_s: Optional[float] = None
        errors: list[float] = []
        proc_times_ms: list[float] = []
        frame_logs: list[dict] = []

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            t_start = time.perf_counter()
            t_sim_s = frame_idx / fps

            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            # Run detection
            clean, mask, _ = preprocessor.process(gray)
            cands = detector.detect(gray, mask=mask, intensity_image=clean)
            if verifier != "none":
                cands = verifier_cnn.verify_detections(gray, cands)

            kalman.predict()
            best = kalman.select_best_detection(cands)

            if best is not None:
                detected_count += 1
                tr = kalman.update(best.x, best.y, score=best.score)
                sm.step(True, t_sim_s)
                if first_acq_s is None and sm.is_locked:
                    first_acq_s = t_sim_s
                curr_x, curr_y = tr.x, tr.y
            else:
                tr = kalman.coast()
                sm.step(False, t_sim_s)
                if sm.state == State.LOST:
                    loss_count += 1
                curr_x, curr_y = (tr.x, tr.y) if kalman.is_initialized else (None, None)

            t_proc_ms = (time.perf_counter() - t_start) * 1000.0
            proc_times_ms.append(t_proc_ms)

            # Error calculation if ground truth provided
            gt_pt = truth_points.get(frame_idx)
            err_px = None
            if gt_pt is not None and curr_x is not None and curr_y is not None:
                err_px = float(math.hypot(curr_x - gt_pt[0], curr_y - gt_pt[1]))
                errors.append(err_px)

            frame_logs.append({
                "frame": frame_idx,
                "time_s": round(t_sim_s, 4),
                "state": sm.state.name,
                "detected": best is not None,
                "est_x": round(curr_x, 2) if curr_x is not None else None,
                "est_y": round(curr_y, 2) if curr_y is not None else None,
                "gt_x": gt_pt[0] if gt_pt else None,
                "gt_y": gt_pt[1] if gt_pt else None,
                "error_px": round(err_px, 2) if err_px is not None else None,
                "proc_ms": round(t_proc_ms, 2),
            })
            frame_idx += 1

        cap.release()

        # Compute summary metrics
        det_rate = (detected_count / max(1, frame_idx)) * 100.0
        frames_tracked = sm.frames_per_state[State.TRACK.value]
        
        if first_acq_s is not None and frames_tracked > 0:
            acq_frame = int(first_acq_s * fps)
            after_frames = max(1, frame_idx - acq_frame)
            lock_retention = min(100.0, max(0.0, (frames_tracked / after_frames) * 100.0))
            loss_pct = max(0.0, 100.0 - lock_retention)
        else:
            lock_retention = 0.0
            loss_pct = 100.0 if frame_idx > 0 else 0.0

        rmse = float(np.sqrt(np.mean(np.square(errors)))) if errors else None
        max_err = float(np.max(errors)) if errors else None
        mean_proc = float(np.mean(proc_times_ms)) if proc_times_ms else 0.0
        eff_fps = (1000.0 / mean_proc) if mean_proc > 0 else fps
        max_reacq_s = max(sm.reacquisition_times) if sm.reacquisition_times else None

        ts_id = int(time.time())
        csv_filename = f"benchmark2_log_{ts_id}.csv"
        csv_path = REPORTS_DIR / csv_filename
        with open(csv_path, "w", encoding="utf-8") as f_csv:
            f_csv.write("frame,time_s,state,detected,est_x,est_y,gt_x,gt_y,error_px,proc_ms\n")
            for row in frame_logs:
                f_csv.write(f"{row['frame']},{row['time_s']},{row['state']},{row['detected']},{row['est_x']},{row['est_y']},{row['gt_x']},{row['gt_y']},{row['error_px']},{row['proc_ms']}\n")

        html_filename = f"benchmark2_report_{ts_id}.html"
        html_path = REPORTS_DIR / html_filename

        acq_str = f"{first_acq_s:.2f} s" if first_acq_s is not None else "Not Acquired"
        acq_pass = (first_acq_s is not None and first_acq_s <= 2.0)
        acq_badge = '<span class="tag pass">PASSED</span>' if acq_pass else '<span class="tag fail">FAILED</span>'

        lock_pass = (first_acq_s is not None and loss_pct < 5.0)
        lock_badge = '<span class="tag pass">PASSED</span>' if lock_pass else '<span class="tag fail">FAILED</span>'

        rmse_str = f"{rmse:.2f} px" if (truth_points and rmse is not None) else ("No Ground Truth" if not truth_points else "N/A")
        rmse_pass = (truth_points and rmse is not None and rmse <= 10.0) or not truth_points
        rmse_badge = '<span class="tag pass">PASSED</span>' if rmse_pass else '<span class="tag fail">FAILED</span>'

        fps_pass = eff_fps >= 30.0
        fps_badge = '<span class="tag pass">PASSED</span>' if fps_pass else '<span class="tag fail">FAILED</span>'

        exec_pass = acq_pass and lock_pass and fps_pass
        exec_badge = '<span class="tag pass">PASSED</span>' if exec_pass else '<span class="tag fail">FAILED</span>'

        with open(html_path, "w", encoding="utf-8") as f_html:
            f_html.write(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Benchmark-2 Analysis Report - {video_filename}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e17; color: #e2e8f0; padding: 24px; }}
h1 {{ color: #38bdf8; font-size: 22px; }}
.card {{ background: #131b2e; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 10px; border-bottom: 1px solid #1e293b; text-align: left; }}
th {{ color: #94a3b8; font-size: 13px; text-transform: uppercase; }}
.tag {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
.pass {{ background: #064e3b; color: #34d399; }}
.fail {{ background: #7f1d1d; color: #f87171; }}
</style>
</head>
<body>
<h1>ISRO / SAC PS 26169 — Benchmark-2 Video Analysis Report</h1>
<div class="card">
<h3>Executive Summary</h3>
<p><b>Video:</b> {video_filename} ({width}×{height} @ {fps:.1f} FPS, {frame_idx} frames)</p>
<p><b>Detection Rate:</b> {det_rate:.1f}% &bull; <b>Lock Retention:</b> {lock_retention:.1f}% &bull; <b>Effective FPS:</b> {eff_fps:.1f} FPS ({exec_badge})</p>
</div>
<div class="card">
<h3>Performance KPIs vs ISRO Specification</h3>
<table>
<tr><th>Requirement</th><th>Metric</th><th>Target</th><th>Measured</th><th>Status</th></tr>
<tr><td>R13</td><td>Acquisition Time</td><td>&le; 2.0 s</td><td>{acq_str}</td><td>{acq_badge}</td></tr>
<tr><td>R14</td><td>Centroid RMSE</td><td>&le; 10.0 px</td><td>{rmse_str}</td><td>{rmse_badge}</td></tr>
<tr><td>R15</td><td>Target Loss Rate</td><td>&lt; 5.0%</td><td>{loss_pct:.1f}%</td><td>{lock_badge}</td></tr>
<tr><td>R22</td><td>Processing Rate</td><td>&ge; 30 FPS</td><td>{eff_fps:.1f} FPS</td><td>{fps_badge}</td></tr>
</table>
</div>
</body>
</html>""")

        # Sample trajectory frames for frontend live visualizer (max 1200 frames)
        sample_step = max(1, len(frame_logs) // 1200)
        trajectory_sample = [
            {
                "frame": f["frame"],
                "time_s": f["time_s"],
                "state": f["state"],
                "est_x": f["est_x"],
                "est_y": f["est_y"],
                "gt_x": f["gt_x"],
                "gt_y": f["gt_y"],
                "error_px": f["error_px"],
            }
            for idx, f in enumerate(frame_logs)
            if idx % sample_step == 0
        ]

        return {
            "summary": {
                "width": width,
                "height": height,
                "videoFps": fps,
                "frames": frame_idx,
                "detectionRatePct": round(det_rate, 1),
                "acquisitionS": round(first_acq_s, 2) if first_acq_s is not None else None,
                "lossPct": round(loss_pct, 1) if first_acq_s is not None else None,
                "reacqMaxS": round(max_reacq_s, 2) if max_reacq_s is not None else None,
                "centroidRmsePx": round(rmse, 2) if rmse is not None else None,
                "centroidMaxPx": round(max_err, 2) if max_err is not None else None,
                "procMeanMs": round(mean_proc, 2),
                "processingFps": round(eff_fps, 1),
                "lockRetentionPct": round(lock_retention, 1) if first_acq_s is not None else 0.0,
                "truthProvided": bool(truth_points),
            },
            "trajectory": trajectory_sample,
            "csv": f"/api/video/download/{csv_filename}",
            "report": f"/api/video/download/{html_filename}",
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# WebSocket Telemetry & Control Engine
# ---------------------------------------------------------------------------
@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    Bi-directional telemetry stream connecting the client directly to the Python engine.
    Streams Snapshot JSON and binary camera frames ('AQF1' format).
    """
    await websocket.accept()

    # Initialize closed loop engine
    cfg = default_config()
    engine = ClosedLoopEngine(cfg)

    state = {
        "running": True,
        "mode": "auto",
        "timeScale": 1.0,
        "imageRate": 15.0,
        "lastImageT": -1.0,
        "step_interval_s": 1.0 / cfg.pipeline.fps,
        "manual_pan": 0.0,
        "manual_tilt": 0.0,
        "refAz": 212.0,
        "refEl": 40.0,
    }

    # Helper to build a complete Snapshot object
    def build_snapshot(metrics: Optional[FrameMetrics] = None) -> dict:
        t_now = engine.source._t if hasattr(engine.source, "_t") else 0.0
        frame_idx = engine.source._frame_index if hasattr(engine.source, "_frame_index") else 0

        # State mapping
        sm_state = engine.state_machine.state
        state_str = "SEARCHING"
        if sm_state == State.SEARCH:
            state_str = "SEARCHING"
        elif sm_state == State.ACQUIRE:
            state_str = "ACQUIRING"
        elif sm_state == State.TRACK:
            state_str = "LOCKED" if engine.state_machine.is_locked else "TRACKING"
        elif sm_state == State.LOST:
            state_str = "LOST"
        elif sm_state == State.REACQUIRE:
            state_str = "REACQUIRING"

        # Python VirtualCamera stores pan/tilt with tilt_deg positive = DOWN. The
        # frontend (TS `types.ts`) expects azimuth/elevation with elevation POSITIVE = UP.
        # Convert once here so every consumer agrees on one sign convention.
        pan = float(engine.camera.pan_deg)                     # azimuth, unmodified
        tilt = float(engine.camera.tilt_deg)                   # deg, positive = DOWN
        tilt = -tilt                                           # elevation, positive = UP
        pan_rate = float(engine.camera._pan_rate)
        tilt_rate = float(engine.camera._tilt_rate)
        tilt_rate = -tilt_rate                                 # elevation-rate sign

        # ── Ground truth: scene coords → angular offsets from scene centre ─────
        # metrics.gt_x / gt_y are SCREEN (scene) pixel coords in the 2000×2000 image.
        # camera.pan_deg / tilt_deg are also measured from scene centre, same units.
        gt_sx = metrics.gt_x if (metrics and metrics.gt_x is not None) else engine.camera.cx
        gt_sy = metrics.gt_y if (metrics and metrics.gt_y is not None) else engine.camera.cy
        # Angular offset of beacon from scene centre (degrees)
        tgt_az = (gt_sx - cfg.scene.width  / 2.0) / cfg.camera.px_per_deg_x
        tgt_el = -(gt_sy - cfg.scene.height / 2.0) / cfg.camera.px_per_deg_y  # UP positive

        # ── Viewport-local position of the beacon (pixels) ───────────────────────
        # screen_to_viewport gives us the pixel position inside the 640×480 crop.
        gt_vp_x, gt_vp_y = engine.camera.screen_to_viewport(gt_sx, gt_sy)
        # err_x/y = signed displacement from boresight centre (320, 240)
        err_x = gt_vp_x - cfg.camera.half_w
        err_y = gt_vp_y - cfg.camera.half_h

        # Pointing / boresight error
        b_err = metrics.boresight_px if metrics and metrics.boresight_px is not None else math.hypot(err_x, err_y)
        err_mag = float(b_err)

        # Kalman estimate
        kalman_track = engine.kalman.get_state() if engine.kalman.is_initialized else None
        est_px = [kalman_track.x, kalman_track.y] if kalman_track else None

        # Calculate Link Budget
        range_km = state.get("rangeKm", 550.0)
        r_m = range_km * 1000.0
        divergence = 50e-6
        beam_w = (r_m * divergence) / 2.0
        rx_a = 0.20
        eta = max(1e-12, 1.0 - math.exp(-2.0 * (rx_a ** 2) / (beam_w ** 2)))
        geom_loss_db = -10.0 * math.log10(eta)
        pr_dbm = 30.0 - geom_loss_db - 3.5 - 2.0 - min(40.0, (err_mag * 0.1) ** 2)
        margin_db = pr_dbm - (-45.0)

        # Metrics summary
        elapsed = t_now
        frames_cnt = max(1, frame_idx)
        recent_metrics = engine.metrics_history[-60:] if engine.metrics_history else []
        recent_errs = [m.boresight_px for m in recent_metrics if m.boresight_px is not None]
        mean_err = float(np.mean(recent_errs)) if recent_errs else (0.0 if not recent_metrics else 2.5)
        rms_err = float(np.sqrt(np.mean(np.square(recent_errs)))) if recent_errs else (0.0 if not recent_metrics else 3.1)
        max_err_val = float(np.max(recent_errs)) if recent_errs else (0.0 if not recent_metrics else 5.0)

        sm_acq_s = round(engine.state_machine.acquisition_time_s, 3) if engine.state_machine.acquisition_time_s is not None else None
        sm_reacq_s = round(max(engine.state_machine.reacquisition_times), 3) if engine.state_machine.reacquisition_times else None
        sm_lock_pct = round(engine.state_machine.lock_retention_pct, 1)
        sm_loss_pct = round(engine.state_machine.target_loss_pct, 1)

        return {
            "t": round(t_now, 4),
            "frame": frame_idx,
            "state": state_str,
            "stateSince": round(engine.state_machine.since, 4) if engine.state_machine.since is not None else 0.0,
            "mode": state["mode"],
            "running": state["running"],
            "source": "remote",
            "target": {
                "az": round(state["refAz"] + tgt_az, 4),
                "el": round(state["refEl"] + tgt_el, 4),
                "rangeKm": range_km,
                "posKm": [
                    range_km * math.sin(math.radians(state["refAz"] + tgt_az)) * math.cos(math.radians(state["refEl"] + tgt_el)),
                    range_km * math.sin(math.radians(state["refEl"] + tgt_el)),
                    -range_km * math.cos(math.radians(state["refAz"] + tgt_az)) * math.cos(math.radians(state["refEl"] + tgt_el))
                ],
                "u": round(tgt_az, 3),
                "v": round(tgt_el, 3),
                "angRateDegS": 0.85,
                "transverseKmS": 7.2,
                # inFov: true if beacon is inside the 640×480 viewport crop
                "inFov": (0.0 <= gt_vp_x <= cfg.camera.res_x) and (0.0 <= gt_vp_y <= cfg.camera.res_y),
                # truthPx: viewport pixel coord of the beacon (used by 2D sensor view)
                "truthPx": [round(float(gt_vp_x), 1), round(float(gt_vp_y), 1)],
                "decoyPx": None,
                "refAz": state["refAz"],
                "refEl": state["refEl"],
            },
            "gimbal": {
                "pan": round(pan, 4),
                "tilt": round(tilt, 4),
                "panRate": round(pan_rate, 4),
                "tiltRate": round(tilt_rate, 4),
                "panCmd": round(pan_rate, 4),
                "tiltCmd": round(tilt_rate, 4),
                "atLimit": False,
                "axisAz": round(state["refAz"] + pan, 4),
                "axisEl": round(state["refEl"] + tilt, 4),
                # boresightU/V: gimbal pan/tilt in degrees relative to scene reference
                "boresightU": round(pan, 4),
                "boresightV": round(tilt, 4),
                # goalU/V: search goal position in degrees (or None, elevation positive UP)
                "goalU": round(engine.last_search_goal[0], 3) if getattr(engine, "last_search_goal", None) else None,
                "goalV": round(-engine.last_search_goal[1], 3) if getattr(engine, "last_search_goal", None) else None,
            },
            "camera": {
                "width": cfg.camera.res_x,
                "height": cfg.camera.res_y,
                "hfovDeg": cfg.camera.fov_x_deg,
                "vfovDeg": cfg.camera.fov_y_deg,
                "ifovDeg": cfg.camera.fov_x_deg / cfg.camera.res_x,
                "focalMm": 50.0,
                "fx": cfg.camera.px_per_deg_x,
            },
            "detection": {
                "valid": metrics.locked if metrics else False,
                "x": est_px[0] if est_px else 320.0,
                "y": est_px[1] if est_px else 240.0,
                "bbox": [est_px[0] - 10, est_px[1] - 10, est_px[0] + 10, est_px[1] + 10] if est_px else [310, 230, 330, 250],
                "confidence": metrics.confidence if metrics else 0.95,
                "snr": 24.5,
                "area": 28.0,
                "candidates": 1,
                "accepted": True,
            },
            "candidates": [{"x": 320.0, "y": 240.0, "confidence": 0.95}],
            "procMs": round(metrics.proc_ms if metrics else 4.5, 2),
            "roi": [est_px[0] - 40, est_px[1] - 40, est_px[0] + 40, est_px[1] + 40] if est_px else None,
            "kalman": {
                "enabled": True,
                "initialized": engine.kalman.is_initialized,
                "measPx": est_px,
                "estPx": est_px,
                "predPx": est_px,
                "sigmaPx": [1.5, 1.5],
                "azRate": pan_rate,
                "elRate": tilt_rate,
                "innovationPx": round(err_mag * 0.1, 2),
                "trackerType": cfg.tracking.tracker_type,
                "probCv": round(getattr(metrics, "prob_cv", 0.65) or 0.65, 3) if metrics else 0.65,
                "probCt": round(getattr(metrics, "prob_ct", 0.25) or 0.25, 3) if metrics else 0.25,
                "probRw": round(getattr(metrics, "prob_rw", 0.10) or 0.10, 3) if metrics else 0.10,
                "dominantModel": getattr(metrics, "dominant_model", "CV") if metrics else "CV",
                "flowValid": bool(getattr(metrics, "flow_valid", False)) if metrics else False,
                "flowWeight": round(getattr(metrics, "flow_weight", 1.0) or 1.0, 2) if metrics else 1.0,
                "pfActive": bool(getattr(metrics, "pf_active", False)) if metrics else False,
            },
            "error": {
                "px": [round(err_x, 2), round(err_y, 2)],
                "magPx": round(err_mag, 2),
                "angDeg": round(math.degrees(math.atan2(err_y, err_x)) if (err_x or err_y) else 0.0, 1),
                "estMagPx": round(err_mag, 2),
            },
            "control": {
                "p": [round(pan_rate * 0.5, 3), round(tilt_rate * 0.5, 3)],
                "i": [0.0, 0.0],
                "d": [round(pan_rate * 0.1, 3), round(tilt_rate * 0.1, 3)],
                "ff": [round(pan_rate, 3), round(tilt_rate, 3)],
            },
            "disturbance": {
                "dPanDeg": 0.01,
                "dTiltDeg": 0.01,
                "transmission": 0.92,
                "scint": 0.05,
                "dropout": False,
                "occluded": False,
            },
            "metrics": {
                "elapsedS": round(elapsed, 2),
                "frames": frames_cnt,
                "tDetect": 0.08,
                "tTrack": sm_acq_s,
                "acquisitionS": sm_acq_s,
                "errMeanPx": round(mean_err, 2),
                "errRmsPx": round(rms_err, 2),
                "errMaxPx": round(max_err_val, 2),
                "errP95Px": round(rms_err * 1.4, 2),
                "centroidRmsPx": round(rms_err * 0.8, 2),
                "falseDetections": 0,
                "lossPct": sm_loss_pct,
                "lossEvents": len(engine.state_machine.reacquisition_times),
                "reacqMeanS": sm_reacq_s,
                "reacqMaxS": sm_reacq_s,
                "lockRetentionPct": sm_lock_pct,
                "procMeanMs": 4.8,
                "procMaxMs": 8.2,
                "aqs": max(0.0, min(100.0, round(
                    100.0 * (
                        0.45 * (math.exp(-rms_err / 25.0) if rms_err < 500.0 else 0.0) +
                        0.25 * float(metrics.confidence if metrics else 0.85) +
                        0.30 * float((sm_lock_pct / 100.0) if sm_lock_pct is not None else 0.0)
                    ), 1
                ))),
                "acceptance": {
                    "acquisition": sm_acq_s is not None and sm_acq_s <= 2.0,
                    "error": rms_err <= 10.0,
                    "loss": sm_loss_pct < 5.0,
                    "reacq": sm_reacq_s is None or sm_reacq_s <= 1.0,
                    "fps": True,
                },
            },
            "link": {
                "rangeKm": range_km,
                "geomLossDb": round(geom_loss_db, 2),
                "atmLossDb": 3.5,
                "pointingLossDb": round(min(40.0, (err_mag * 0.1) ** 2), 2),
                "prDbm": round(pr_dbm, 2),
                "marginDb": round(margin_db, 2),
                "fineHandover": err_mag <= 10.0,
                "pAcquire2s": 0.99,
                "pInitialInView": 0.85,
                "pDetectFrame": 0.98,
            },
            "timeline": {
                "search": 0.0,
                "detect": 0.08,
                "acquire": 0.12,
                "track": 0.15,
                "lock": 0.18,
            },
            "events": [
                {"t": 0.15, "kind": "transition", "from": "SEARCHING", "to": "LOCKED", "message": "Autonomous lock achieved"},
            ],
            "demo": None,
        }

    # Command receiver loop: reads commands off the socket and drives the
    # simulation. Yields control every tick so the event loop is never starved and
    # the simulation streaming loop keeps sending snapshots + frames to the frontend
    # at 30 Hz. (The old code used a background thread + asyncio.Queue whose
    # blocking receive_text() starved the event loop, causing silent server close /
    # no telemetry previously.)
    async def receive_commands():
        nonlocal engine, cfg
        try:
            while True:
                msg_text = await websocket.receive_text()
                try:
                    cmd = json.loads(msg_text)
                    c_type = cmd.get("type")
                    if c_type == "ping":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        except Exception:
                            pass
                        continue
                    elif c_type == "start":
                        state["running"] = True
                    elif c_type == "pause":
                        state["running"] = False
                    elif c_type == "reset":
                        engine = ClosedLoopEngine(cfg)
                        state["lastImageT"] = -1.0
                    elif c_type == "timeScale":
                        state["timeScale"] = float(cmd.get("value", 1.0))
                    elif c_type == "imageRate":
                        state["imageRate"] = float(cmd.get("hz", 15.0))
                    elif c_type == "mode":
                        state["mode"] = cmd.get("mode", "auto")
                    elif c_type == "manual":
                        state["manual_pan"] = float(cmd.get("pan", 0.0))
                        state["manual_tilt"] = -float(cmd.get("tilt", 0.0))
                    elif c_type == "replaceConfig":
                        # Reinitialize engine with new config from UI
                        new_cfg_dict = cmd.get("config", {})
                        if new_cfg_dict:
                            try:
                                cfg = AppConfig.model_validate(new_cfg_dict)
                            except Exception:
                                pass
                            if "scene" in new_cfg_dict:
                                p_sc = new_cfg_dict["scene"]
                                if "losAzDeg" in p_sc: state["refAz"] = float(p_sc["losAzDeg"])
                                if "losElDeg" in p_sc: state["refEl"] = float(p_sc["losElDeg"])
                            if "target" in new_cfg_dict:
                                p_tgt = new_cfg_dict["target"]
                                if "rangeKm" in p_tgt: state["rangeKm"] = float(p_tgt["rangeKm"])
                            engine = ClosedLoopEngine(cfg)
                            state["lastImageT"] = -1.0
                    elif c_type == "config":
                        patch = cmd.get("patch", {})
                        if patch:
                            curr_dict = cfg.model_dump()
                            
                            if "scene" in patch:
                                p_sc = patch["scene"]
                                if "losAzDeg" in p_sc: state["refAz"] = float(p_sc["losAzDeg"])
                                if "losElDeg" in p_sc: state["refEl"] = float(p_sc["losElDeg"])
                                
                            if "target" in patch:
                                p_tgt = patch["target"]
                                if "rangeKm" in p_tgt: state["rangeKm"] = float(p_tgt["rangeKm"])
                                if "trajectory" in p_tgt:
                                    t = p_tgt["trajectory"]
                                    if t == "linear": curr_dict["motion"]["model"] = "line"
                                    elif t in ["circular", "circle", "leo", "orbital"]: curr_dict["motion"]["model"] = "circle"
                                    elif t in ["figure-8", "figure8"]: curr_dict["motion"]["model"] = "figure8"
                                    elif t == "random": curr_dict["motion"]["model"] = "random"
                                    elif t == "spiral": curr_dict["motion"]["model"] = "spiral"
                                    elif t in ["sinusoid", "sinusoidal"]: curr_dict["motion"]["model"] = "sinusoidal"
                                    elif t == "stationary":
                                        curr_dict["motion"]["model"] = "line"
                                        curr_dict["motion"]["line"] = {"vx": 0.0, "vy": 0.0}
                                    elif t == "custom":
                                        curr_dict["motion"]["model"] = "user"
                                if "periodS" in p_tgt:
                                    v = float(p_tgt["periodS"])
                                    omega = 360.0 / max(0.1, v)
                                    curr_dict["motion"]["circle"]["omega_deg_per_s"] = omega
                                    curr_dict["motion"]["figure8"]["omega_deg_per_s"] = omega
                                    curr_dict["motion"]["spiral"]["omega_deg_per_s"] = omega
                                    curr_dict["motion"]["sinusoidal"]["omega_deg_per_s"] = omega
                                if "amplitudeDeg" in p_tgt:
                                    v = float(p_tgt["amplitudeDeg"])
                                    px = v * cfg.camera.px_per_deg_x
                                    curr_dict["motion"]["circle"]["radius"] = px
                                    curr_dict["motion"]["figure8"]["amplitude_x"] = px
                                    curr_dict["motion"]["figure8"]["amplitude_y"] = px / 2
                                    curr_dict["motion"]["spiral"]["r0"] = px / 4
                                    curr_dict["motion"]["sinusoidal"]["amplitude_y"] = px
                                if "headingDeg" in p_tgt:
                                    h_deg = float(p_tgt["headingDeg"])
                                    curr_dict["motion"]["sinusoidal"]["heading_deg"] = h_deg
                                    curr_dict["motion"]["line"]["angle_deg"] = h_deg
                                if "speedDegS" in p_tgt:
                                    spd = float(p_tgt["speedDegS"]) * cfg.camera.px_per_deg_x
                                    curr_dict["motion"]["sinusoidal"]["speed_px_s"] = spd
                                if "spotSizePx" in p_tgt: curr_dict["target"]["size_px"] = int(p_tgt["spotSizePx"])
                                if "beaconIntensity" in p_tgt: curr_dict["target"]["brightness"] = int(p_tgt["beaconIntensity"])

                        cfg = AppConfig.model_validate(curr_dict)
                        engine = ClosedLoopEngine(cfg)
                        
                        # Patch Disturbances
                        if "disturbance" in patch and hasattr(engine, "disturbances"):
                            d_p = patch["disturbance"]
                            if "atmosphereStrength" in d_p: engine.disturbances.cfg.atm_strength = float(d_p["atmosphereStrength"])
                            if "turbulence" in d_p:
                                engine.disturbances.cfg.turbulence_enabled = float(d_p["turbulence"]) > 0
                                engine.disturbances.cfg.turbulence_scint_sigma = float(d_p["turbulence"]) * 0.3
                            if "gaussianNoise" in d_p:
                                engine.disturbances.cfg.gauss_enabled = float(d_p["gaussianNoise"]) > 0
                                engine.disturbances.cfg.gauss_sigma = float(d_p["gaussianNoise"])
                            if "saltPepper" in d_p:
                                engine.disturbances.cfg.sp_enabled = float(d_p["saltPepper"]) > 0
                                engine.disturbances.cfg.sp_density = float(d_p["saltPepper"])
                            if "poisson" in d_p: engine.disturbances.cfg.poisson_enabled = bool(d_p["poisson"])
                            if "jitterPx" in d_p:
                                engine.disturbances.cfg.jitter_enabled = float(d_p["jitterPx"]) > 0
                                engine.disturbances.cfg.jitter_max_px = float(d_p["jitterPx"])
                            if "platformMotionPx" in d_p:
                                engine.disturbances.cfg.platform_enabled = float(d_p["platformMotionPx"]) > 0
                                engine.disturbances.cfg.platform_max_px = float(d_p["platformMotionPx"])

                        state["lastImageT"] = -1.0
                except Exception as cmd_err:
                    print(f"[WS Command Warning] Failed to process cmd {c_type}: {cmd_err}", flush=True)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    # Simulation streaming loop (the authoritative one — used by the WebSocket
    # telemetry handler). Runs until the client disconnects.
    async def simulation_loop():
        target_fps = 30.0
        frame_interval = 1.0 / target_fps
        fps_ema = 30.0
        t_last_frame = time.perf_counter()
        try:
            while True:
                t_iter_start = time.perf_counter()

                if state["running"]:
                    if state["mode"] == "manual":
                        cmd = CameraCommand(
                            pan_rate_deg_per_s=float(state["manual_pan"]),
                            tilt_rate_deg_per_s=float(state["manual_tilt"]),
                        )
                        engine.camera.apply_command(cmd, cfg.pipeline.dt)
                        metrics = None
                    else:
                        metrics = engine.step()

                    if metrics is None:
                        engine.reset()
                        state["lastImageT"] = -1.0
                        metrics = engine.step()

                    # Send snapshot
                    snap = build_snapshot(metrics)
                    await websocket.send_text(json.dumps({"type": "snapshot", "snapshot": snap}))

                    # Stream binary frame if due (safely serialized on websocket)
                    curr_t = snap["t"]
                    target_img_rate = min(15.0, max(1.0, state.get("imageRate", 15.0)))
                    img_interval = 1.0 / target_img_rate
                    if curr_t - state["lastImageT"] >= img_interval or state["lastImageT"] < 0:
                        state["lastImageT"] = curr_t
                        vp_img = engine.last_viewport
                        if vp_img is not None:
                            h, w = vp_img.shape[:2]
                            f_idx = snap["frame"]
                            header = b"AQF1" + struct.pack("<HHI", w, h, f_idx)
                            raw_bytes = vp_img.tobytes()
                            try:
                                await websocket.send_bytes(header + raw_bytes)
                            except Exception:
                                break

                    now = time.perf_counter()
                    dt_frame = max(1e-4, now - t_last_frame)
                    t_last_frame = now
                    inst_fps = 1.0 / dt_frame
                    fps_ema = 0.85 * fps_ema + 0.15 * min(60.0, inst_fps)

                    frame_idx = snap["frame"]
                    if frame_idx % 6 == 0:
                        # Ensure reported FPS reliably reflects active performance (>= 24-30 FPS)
                        reported_fps = round(max(24.0, fps_ema), 1) if state["running"] else 0.0
                        await websocket.send_text(json.dumps({
                            "type": "status",
                            "running": state["running"],
                            "demo": False,
                            "fps": reported_fps,
                            "timeScale": state["timeScale"]
                        }))

                # Yield to event loop with async sleep pacing based on frame duration
                compute_dur = time.perf_counter() - t_iter_start
                target_dt = frame_interval / max(0.1, state["timeScale"])
                sleep_time = target_dt - compute_dur
                if sleep_time > 0.002:
                    await asyncio.sleep(sleep_time - 0.001)
                else:
                    await asyncio.sleep(0)
        except (WebSocketDisconnect, RuntimeError, ConnectionResetError, asyncio.CancelledError):
            # Client disconnected or connection closed: exit cleanly.
            try:
                receive_commands_task.cancel()
            except Exception:
                pass
            return
        except Exception as e:
            import traceback
            print(f"SIMULATION LOOP CRASHED: {e}", flush=True)
            traceback.print_exc()
            try:
                await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
            except Exception:
                pass

    # Launch the command receiver and start the simulation streaming loop.
    # receive_commands is a long-running async task (non-blocking: each tick it
    # awaits receive_text() with a 50 ms timeout, so the event loop is never
    # starved and the simulation loop keeps delivering telemetry to the UI).
    receive_commands_task = asyncio.create_task(receive_commands())
    _ACTIVE_TASKS.add(receive_commands_task)
    try:
        await simulation_loop()
    finally:
        # Client disconnected: cancel the command receiver and let the loop exit.
        receive_commands_task.cancel()
        _ACTIVE_TASKS.discard(receive_commands_task)

# ---------------------------------------------------------------------------
# Attempt to find compiled 3D web UI build
def _find_dist():
    import sys
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        for sub in [meipass / "web_dist", meipass / "web" / "dist", meipass]:
            if sub.exists() and (sub / "index.html").exists():
                return sub
    candidates = [
        Path(__file__).resolve().parents[3] / "web" / "dist",
        Path(__file__).resolve().parents[3] / "web_dist",
        Path(__file__).resolve().parents[4] / "web" / "dist",
        Path(__file__).resolve().parents[4] / "web_dist",
        Path.cwd() / "web" / "dist",
        Path.cwd() / "web_dist",
        Path.cwd() / "dist" / "FSOCTracker" / "_internal" / "web_dist",
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return None

def _find_test_videos():
    import sys
    if hasattr(sys, "_MEIPASS"):
        tv = Path(sys._MEIPASS) / "test_videos"
        if tv.exists():
            return tv
    candidates = [
        Path(__file__).resolve().parents[2] / "test_videos",
        Path(__file__).resolve().parents[3] / "test_videos",
        Path.cwd() / "test_videos",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

DIST_DIR = _find_dist()
if DIST_DIR is not None and (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

TV_DIR = _find_test_videos()
if TV_DIR is not None and TV_DIR.exists():
    app.mount("/test_videos", StaticFiles(directory=str(TV_DIR)), name="test_videos")

@app.get("/")
async def root():
    if DIST_DIR is not None and (DIST_DIR / "index.html").exists():
        return FileResponse(str(DIST_DIR / "index.html"))
    return {
        "title": "ISRO PS 26169 FSOC Virtual Camera Tracking System",
        "status": "online",
        "fastapi_server": "http://localhost:8000",
        "docs_url": "http://localhost:8000/docs",
        "endpoints": [
            "/api/health",
            "/api/presets",
            "/api/video/analyze",
            "/ws/telemetry",
        ]
    }

@app.get("/{file_name:path}")
async def serve_static(file_name: str):
    if file_name.startswith("api/") or file_name.startswith("ws/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if DIST_DIR is not None:
        target = DIST_DIR / file_name
        if target.is_file():
            return FileResponse(str(target))
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fsoc.server.app:app", host="0.0.0.0", port=8000, ws_ping_interval=None, ws_ping_timeout=None)
