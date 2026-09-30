"""
profile_breakdown.py
====================
Detailed, high-precision performance profiler for ISRO PS 26169 FSOC Tracking System (Step 5).
Measures latencies (mean, median, P95, P99, max, FPS, CPU time, memory) across every individual component
under both nominal and maximum combined disturbance stress.
Outputs: performance_results.json and performance_results.csv.
"""
import sys
import time
import json
import csv
import psutil
from pathlib import Path
import numpy as np

_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fsoc.core.config import default_config
from fsoc.core.engine import ClosedLoopEngine
from fsoc.simulation.sim_source import SimulatedSource
from fsoc.disturbances.engine import DisturbanceEngine
from fsoc.vision.preprocess import VisionPreprocessor
from fsoc.vision.detector import SpotDetector
from fsoc.vision.cnn_verifier import BeaconVerifierCNN
from fsoc.vision.optical_flow import OpticalFlowTracker
from fsoc.tracking.imm import IMMTracker
from fsoc.vision.flow_gating import AdaptiveFlowGater
from fsoc.tracking.particle_filter import ParticleFilter
from fsoc.control.pid_controller import PIDController


def compute_stats(latencies_ms: list[float]) -> dict:
    arr = np.array(latencies_ms, dtype=np.float64)
    mean_ms = float(np.mean(arr))
    median_ms = float(np.median(arr))
    p95_ms = float(np.percentile(arr, 95))
    p99_ms = float(np.percentile(arr, 99))
    max_ms = float(np.max(arr))
    fps = 1000.0 / mean_ms if mean_ms > 0 else 0.0
    return {
        "mean_ms": round(mean_ms, 4),
        "median_ms": round(median_ms, 4),
        "p95_ms": round(p95_ms, 4),
        "p99_ms": round(p99_ms, 4),
        "max_ms": round(max_ms, 4),
        "fps": round(fps, 2),
    }


def run_profiling(n_frames: int = 150) -> dict:
    proc = psutil.Process()
    mem_start_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"--- Profiling FSOC Tracking Pipeline across {n_frames} frames ---")
    print(f"Initial Memory: {mem_start_mb:.2f} MB")

    cfg = default_config()
    cfg.pipeline.duration_s = float(n_frames / 30.0) + 1.0
    cfg.motion.model = "figure8"
    cfg.target.initial_x = 1000.0
    cfg.target.initial_y = 1000.0

    # 1. Scene Generation (2000x2000)
    source = SimulatedSource(cfg)
    t_scene = []
    frames = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        f = source.next_frame()
        t1 = time.perf_counter()
        t_scene.append((t1 - t0) * 1000.0)
        frames.append(f)

    # 2. Camera Viewport Rendering (640x480 crop)
    engine = ClosedLoopEngine(cfg)
    t_camera_crop = []
    vp_frames = []
    for f in frames:
        t0 = time.perf_counter()
        vp = engine.camera.render(f)
        t1 = time.perf_counter()
        t_camera_crop.append((t1 - t0) * 1000.0)
        vp_frames.append(vp)

    # 3. Disturbance Generation (Individual and Combined)
    dist_engine = DisturbanceEngine(seed=42)
    dist_engine.gaussian.enabled = True
    dist_engine.gaussian.sigma = 15.0
    dist_engine.salt_pepper.enabled = True
    dist_engine.salt_pepper.density = 0.10
    dist_engine.poisson.enabled = True
    dist_engine.poisson.gain = 1.0
    dist_engine.jitter.enabled = True
    dist_engine.jitter.max_px = 15.0
    dist_engine.atmosphere.set_condition("fog", strength=0.60)

    t_dist_viewport = []
    t_dist_gauss = []
    t_dist_sp = []
    t_dist_poisson = []
    t_dist_fog = []
    t_dist_jitter = []
    disturbed_vps = []

    for vp in vp_frames:
        img = vp.image
        # Individual profiling
        t0 = time.perf_counter()
        i_fog = dist_engine.atmosphere.apply(img)
        t1 = time.perf_counter()
        t_dist_fog.append((t1 - t0) * 1000.0)

        t0 = time.perf_counter()
        i_jit = dist_engine.jitter.apply(i_fog)
        t1 = time.perf_counter()
        t_dist_jitter.append((t1 - t0) * 1000.0)

        t0 = time.perf_counter()
        i_sp = dist_engine.salt_pepper.apply(i_jit)
        t1 = time.perf_counter()
        t_dist_sp.append((t1 - t0) * 1000.0)

        t0 = time.perf_counter()
        i_gauss = dist_engine.gaussian.apply(i_sp)
        t1 = time.perf_counter()
        t_dist_gauss.append((t1 - t0) * 1000.0)

        t0 = time.perf_counter()
        i_pois = dist_engine.poisson.apply(i_gauss)
        t1 = time.perf_counter()
        t_dist_poisson.append((t1 - t0) * 1000.0)

        # Full viewport pipeline (Fog + Jitter + S&P + Gauss)
        t0 = time.perf_counter()
        d_img = dist_engine.apply_viewport(img)
        t1 = time.perf_counter()
        t_dist_viewport.append((t1 - t0) * 1000.0)
        disturbed_vps.append(d_img)

    # 4. Perception: Preprocessing
    preproc = VisionPreprocessor(cfg)
    t_preproc = []
    clean_images = []
    masks = []
    for d_img in disturbed_vps:
        t0 = time.perf_counter()
        clean_img, mask, _ = preproc.process(d_img)
        t1 = time.perf_counter()
        t_preproc.append((t1 - t0) * 1000.0)
        clean_images.append(clean_img)
        masks.append(mask)

    # 5. Perception: Spot Detection
    detector = SpotDetector(cfg, preprocessor=preproc)
    t_detector = []
    candidates_list = []
    for d_img, mask, c_img in zip(disturbed_vps, masks, clean_images):
        t0 = time.perf_counter()
        cands = detector.detect(d_img, mask=mask, intensity_image=c_img)
        t1 = time.perf_counter()
        t_detector.append((t1 - t0) * 1000.0)
        candidates_list.append(cands)

    # 6. Perception: CNN Verification
    verifier = BeaconVerifierCNN(cfg)
    t_verifier = []
    verified_list = []
    for d_img, cands in zip(disturbed_vps, candidates_list):
        t0 = time.perf_counter()
        ver = verifier.verify_detections(d_img, cands)
        t1 = time.perf_counter()
        t_verifier.append((t1 - t0) * 1000.0)
        verified_list.append(ver)

    # 7. Optical Flow
    of_tracker = OpticalFlowTracker(cfg.vision.optical_flow, dt=cfg.pipeline.dt)
    t_of = []
    flow_results = []
    for d_img in disturbed_vps:
        t0 = time.perf_counter()
        f_res = of_tracker.estimate_flow(
            curr_img=d_img,
            curr_pan_deg=0.0,
            curr_tilt_deg=0.0,
            hint_pos=(320.0, 240.0),
            px_per_deg_x=160.0,
            px_per_deg_y=160.0,
        )
        t1 = time.perf_counter()
        t_of.append((t1 - t0) * 1000.0)
        flow_results.append(f_res)

    # 8. Adaptive Flow Gating
    gater = AdaptiveFlowGater(dt=cfg.pipeline.dt)
    t_gating = []
    for f_res in flow_results:
        t0 = time.perf_counter()
        _ = gater.evaluate_flow(
            f_res,
            pred_vx=5.0,
            pred_vy=5.0,
            pred_var_vx=25.0,
            pred_var_vy=25.0,
        )
        t1 = time.perf_counter()
        t_gating.append((t1 - t0) * 1000.0)

    # 9. Tracking: IMM (Predict + Update)
    imm = IMMTracker(cfg, dt=cfg.pipeline.dt)
    imm.init_track(320.0, 240.0)
    t_imm_predict = []
    t_imm_update = []
    for ver, flow in zip(verified_list, flow_results):
        t0 = time.perf_counter()
        pred_x, pred_y = imm.predict()
        t1 = time.perf_counter()
        t_imm_predict.append((t1 - t0) * 1000.0)

        best_det = ver[0] if ver else None
        t0 = time.perf_counter()
        if best_det:
            imm.update(best_det.x, best_det.y, score=best_det.score, flow=flow)
        else:
            imm.coast(flow=flow)
        t1 = time.perf_counter()
        t_imm_update.append((t1 - t0) * 1000.0)

    # 10. Tracking: Particle Filter (Dormant vs Active)
    pf = ParticleFilter(cfg, dt=cfg.pipeline.dt, seed=42)
    t_pf_dormant = []
    for ver in verified_list:
        t0 = time.perf_counter()
        if pf.is_active:
            pf.predict()
            pf.update(ver)
        else:
            _ = pf.get_state()
        t1 = time.perf_counter()
        t_pf_dormant.append((t1 - t0) * 1000.0)

    # Active PF profiling
    pf.initialize(center_x=320.0, center_y=240.0)
    t_pf_active = []
    for ver in verified_list:
        t0 = time.perf_counter()
        pf.predict()
        pf.update(ver)
        t1 = time.perf_counter()
        t_pf_active.append((t1 - t0) * 1000.0)

    # 11. Controller: PID
    controller = PIDController(cfg, camera_cfg=cfg.camera, dt=cfg.pipeline.dt)
    t_pid = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        cmd = controller.compute(320.5, 240.2, 10.0, -5.0, state="TRACK")
        t1 = time.perf_counter()
        t_pid.append((t1 - t0) * 1000.0)

    # 12. Complete Closed-Loop: Nominal vs Combined Stress
    nominal_engine = ClosedLoopEngine(cfg)
    t_closed_loop_nominal = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        m = nominal_engine.step()
        t1 = time.perf_counter()
        if m is not None:
            t_closed_loop_nominal.append((t1 - t0) * 1000.0)

    stress_engine = ClosedLoopEngine(cfg)
    stress_engine.disturbances.gaussian.enabled = True
    stress_engine.disturbances.gaussian.sigma = 15.0
    stress_engine.disturbances.salt_pepper.enabled = True
    stress_engine.disturbances.salt_pepper.density = 0.10
    stress_engine.disturbances.jitter.enabled = True
    stress_engine.disturbances.jitter.max_px = 15.0
    stress_engine.disturbances.atmosphere.set_condition("fog", strength=0.60)

    t_closed_loop_stress = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        m = stress_engine.step()
        t1 = time.perf_counter()
        if m is not None:
            t_closed_loop_stress.append((t1 - t0) * 1000.0)

    mem_end_mb = proc.memory_info().rss / (1024 * 1024)
    mem_delta_mb = mem_end_mb - mem_start_mb

    report = {
        "Scene Generation (2000x2000)": compute_stats(t_scene),
        "Camera Viewport Crop (640x480)": compute_stats(t_camera_crop),
        "Disturbances - Fog (Atmosphere)": compute_stats(t_dist_fog),
        "Disturbances - Jitter": compute_stats(t_dist_jitter),
        "Disturbances - Salt & Pepper": compute_stats(t_dist_sp),
        "Disturbances - Gaussian Noise": compute_stats(t_dist_gauss),
        "Disturbances - Poisson Noise": compute_stats(t_dist_poisson),
        "Disturbances - Combined Viewport": compute_stats(t_dist_viewport),
        "Vision - Preprocessing (Median+TopHat+MAD)": compute_stats(t_preproc),
        "Vision - Spot Detection": compute_stats(t_detector),
        "Vision - CNN Verification": compute_stats(t_verifier),
        "Vision - Local LK Optical Flow": compute_stats(t_of),
        "Tracking - Adaptive Flow Gating": compute_stats(t_gating),
        "Tracking - IMM Predict": compute_stats(t_imm_predict),
        "Tracking - IMM Update/Coast": compute_stats(t_imm_update),
        "Tracking - Particle Filter (Dormant TRACK)": compute_stats(t_pf_dormant),
        "Tracking - Particle Filter (Active N=150)": compute_stats(t_pf_active),
        "Control - Predictive PID": compute_stats(t_pid),
        "Complete Closed-Loop Step (Nominal)": compute_stats(t_closed_loop_nominal),
        "Complete Closed-Loop Step (Combined Stress)": compute_stats(t_closed_loop_stress),
    }

    print("\n" + "=" * 115)
    print(f"{'Component / Subsystem':<48} | {'Mean (ms)':<9} | {'Median':<8} | {'P95 (ms)':<9} | {'P99 (ms)':<9} | {'Max (ms)':<9} | {'FPS':<6}")
    print("-" * 115)
    for name, s in report.items():
        print(f"{name:<48} | {s['mean_ms']:<9.3f} | {s['median_ms']:<8.3f} | {s['p95_ms']:<9.3f} | {s['p99_ms']:<9.3f} | {s['max_ms']:<9.3f} | {s['fps']:<6.1f}")
    print("=" * 115)
    print(f"Memory RSS: Start={mem_start_mb:.2f} MB, End={mem_end_mb:.2f} MB, Delta={mem_delta_mb:.2f} MB\n")

    # Export JSON
    with open("performance_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Export CSV
    with open("performance_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Component", "Mean (ms)", "Median (ms)", "P95 (ms)", "P99 (ms)", "Max (ms)", "FPS"])
        for name, s in report.items():
            writer.writerow([name, s["mean_ms"], s["median_ms"], s["p95_ms"], s["p99_ms"], s["max_ms"], s["fps"]])

    return report


if __name__ == "__main__":
    run_profiling(150)
