"""
run_ablation.py
===============
Rigorous 4-Way Scientific Ablation Experiment for Step 4:
A. IMM Filter (CV + CT + RW without Optical Flow, without PF)
B. IMM Filter + Optical Flow (Fixed OF, without PF)
C. IMM Filter + Adaptive Optical Flow (Step 3 system without PF)
D. IMM Filter + Adaptive Optical Flow + Particle Filter (Step 4 complete system)

Runs identical seeds (seed=42), trajectories, disturbances, and durations for a 1:1 scientific comparison.

Conditions Evaluated:
1. Clean (Baseline clear sky)
2. Gaussian Noise (sigma = 15.0 px)
3. Salt & Pepper Noise (10% impulse density)
4. Atmospheric Fog (strength = 0.70)
5. Low Light (faint target brightness = 60)
6. Camera Jitter (+/- 20 px/frame)
7. Platform Motion Drift (+/- 20 px/frame)
8. Complex Figure-8 Maneuver
9. Fast Target (112 px/s)
10. Target Dropout & Occlusion (0.30s occlusion = 9 consecutive frames)
11. Maneuvering Target Under Occlusion (Dropout + Turn maneuver)
12. Combined Stress Test (S&P + Gaussian + Jitter + Fog)
"""
import sys
import json
import time
from pathlib import Path
import numpy as np

# Ensure path
_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fsoc.core.config import default_config
from fsoc.core.engine import ClosedLoopEngine


CONDITIONS = [
    {
        "name": "1. Clean (Clear Sky)",
        "motion": "circle",
        "duration": 2.5,
        "setup": lambda cfg, eng: None,
    },
    {
        "name": "2. Gaussian Noise (sigma=15)",
        "motion": "circle",
        "duration": 2.5,
        "setup": lambda cfg, eng: (
            setattr(eng.disturbances.gaussian, "enabled", True),
            setattr(eng.disturbances.gaussian, "sigma", 15.0),
        ),
    },
    {
        "name": "3. Salt & Pepper (10% density)",
        "motion": "circle",
        "duration": 2.5,
        "setup": lambda cfg, eng: (
            setattr(eng.disturbances.salt_pepper, "enabled", True),
            setattr(eng.disturbances.salt_pepper, "density", 0.10),
        ),
    },
    {
        "name": "4. Atmospheric Fog (str=0.70)",
        "motion": "circle",
        "duration": 2.5,
        "setup": lambda cfg, eng: eng.disturbances.atmosphere.set_condition("fog", strength=0.70),
    },
    {
        "name": "5. Low Light Target (b=60)",
        "motion": "circle",
        "duration": 2.5,
        "setup": lambda cfg, eng: setattr(cfg.target, "brightness", 60),
    },
    {
        "name": "6. Camera Jitter (+/-20px)",
        "motion": "line",
        "duration": 2.5,
        "setup": lambda cfg, eng: (
            setattr(eng.disturbances.jitter, "enabled", True),
            setattr(eng.disturbances.jitter, "max_px", 20.0),
        ),
    },
    {
        "name": "7. Platform Drift (+/-20px)",
        "motion": "random",
        "duration": 2.5,
        "setup": lambda cfg, eng: eng.disturbances.platform.enable_mode("linear", max_shift=20.0),
    },
    {
        "name": "8. Complex Figure-8 Motion",
        "motion": "figure8",
        "duration": 2.5,
        "setup": lambda cfg, eng: None,
    },
    {
        "name": "9. Fast Target (112 px/s)",
        "motion": "line",
        "duration": 2.5,
        "setup": lambda cfg, eng: (
            setattr(cfg.motion.line, "vx", 100.0),
            setattr(cfg.motion.line, "vy", 50.0),
        ),
    },
    {
        "name": "10. Target Occlusion (9 frames)",
        "motion": "line",
        "duration": 3.0,
        "setup": lambda cfg, eng: (
            setattr(cfg.motion.line, "vx", 30.0),
            setattr(cfg.motion.line, "vy", 15.0),
            eng.source.occlusion_intervals.append((1.0, 1.3)),
        ),
    },
    {
        "name": "11. Maneuver Under Occlusion",
        "motion": "circle",
        "duration": 3.0,
        "setup": lambda cfg, eng: (
            eng.source.occlusion_intervals.append((1.0, 1.35)),
        ),
    },
    {
        "name": "12. Combined Stress",
        "motion": "figure8",
        "duration": 2.5,
        "setup": lambda cfg, eng: (
            setattr(eng.disturbances.gaussian, "enabled", True),
            setattr(eng.disturbances.gaussian, "sigma", 15.0),
            setattr(eng.disturbances.salt_pepper, "enabled", True),
            setattr(eng.disturbances.salt_pepper, "density", 0.10),
            setattr(eng.disturbances.jitter, "enabled", True),
            setattr(eng.disturbances.jitter, "max_px", 15.0),
            eng.disturbances.atmosphere.set_condition("fog", strength=0.60),
        ),
    },
]


def run_condition(cond: dict, tracker_mode: str, seed: int = 42) -> dict:
    """
    tracker_mode:
      - 'imm': A. IMM Filter (OF disabled, PF disabled)
      - 'imm_of_fixed': B. IMM Filter + Fixed Optical Flow (PF disabled)
      - 'imm_of_adaptive': C. IMM Filter + Adaptive Optical Flow (PF disabled)
      - 'imm_of_adaptive_pf': D. IMM Filter + Adaptive Optical Flow + Particle Filter (Step 4)
    """
    cfg = default_config()
    cfg.pipeline.seed = seed
    cfg.pipeline.duration_s = cond["duration"]
    cfg.motion.model = cond["motion"]
    cfg.target.initial_x = 1000.0
    cfg.target.initial_y = 1000.0
    cfg.target.brightness = 230

    if tracker_mode == "imm":
        cfg.tracking.tracker_type = "imm"
        cfg.vision.optical_flow.enabled = False
        cfg.tracking.adaptive_flow.enabled = False
        cfg.tracking.particle_filter.enabled = False
    elif tracker_mode == "imm_of_fixed":
        cfg.tracking.tracker_type = "imm"
        cfg.vision.optical_flow.enabled = True
        cfg.tracking.adaptive_flow.enabled = False
        cfg.tracking.particle_filter.enabled = False
    elif tracker_mode == "imm_of_adaptive":
        cfg.tracking.tracker_type = "imm"
        cfg.vision.optical_flow.enabled = True
        cfg.tracking.adaptive_flow.enabled = True
        cfg.tracking.particle_filter.enabled = False
    elif tracker_mode == "imm_of_adaptive_pf":
        cfg.tracking.tracker_type = "imm"
        cfg.vision.optical_flow.enabled = True
        cfg.tracking.adaptive_flow.enabled = True
        cfg.tracking.particle_filter.enabled = True
    else:
        raise ValueError(f"Unknown tracker_mode: {tracker_mode}")

    engine = ClosedLoopEngine(cfg)
    cond["setup"](cfg, engine)

    max_frames = int(cond["duration"] * cfg.pipeline.fps)
    t0 = time.perf_counter()
    summary = engine.run(max_frames=max_frames)
    total_wall_ms = (time.perf_counter() - t0) * 1000.0

    locked_errors = [m.error_px for m in engine.metrics_history if m.locked and m.error_px is not None]
    all_errors = [m.error_px for m in engine.metrics_history if m.error_px is not None]
    err_eval = locked_errors if locked_errors else all_errors

    err_arr = np.array(err_eval, dtype=np.float64) if err_eval else np.array([0.0])
    mean_err = float(np.mean(err_arr))
    rmse_err = float(np.sqrt(np.mean(np.square(err_arr))))
    p95_err = float(np.percentile(err_arr, 95))
    max_err = float(np.max(err_arr))

    cv_probs = [m.prob_cv for m in engine.metrics_history if m.prob_cv > 0]
    ct_probs = [m.prob_ct for m in engine.metrics_history if m.prob_ct > 0]
    rw_probs = [m.prob_rw for m in engine.metrics_history if m.prob_rw > 0]

    flow_weights = [m.flow_weight for m in engine.metrics_history]
    mean_flow_weight = float(np.mean(flow_weights)) if flow_weights else 0.0
    flow_valids = [m.flow_valid for m in engine.metrics_history]
    flow_valid_pct = float(np.mean(flow_valids) * 100.0) if flow_valids else 0.0

    pf_actives = [m.pf_active for m in engine.metrics_history]
    pf_active_pct = float(np.mean(pf_actives) * 100.0) if pf_actives else 0.0
    pf_reacquired_count = sum(1 for m in engine.metrics_history if m.pf_reacquired)

    return {
        "tracker": tracker_mode,
        "condition": cond["name"],
        "mean_error_px": mean_err,
        "rmse_error_px": rmse_err,
        "p95_error_px": p95_err,
        "max_error_px": max_err,
        "target_loss_pct": summary.target_loss_pct,
        "reacquisition_success_pct": summary.reacquisition_success_pct,
        "reacquisition_time_mean_s": summary.reacquisition_time_mean_s,
        "reacquisition_time_p95_s": summary.reacquisition_time_p95_s,
        "reacquisition_time_max_s": summary.reacquisition_time_max_s,
        "false_reacquisition_count": summary.false_reacquisition_count,
        "lock_pct": summary.lock_retention_pct,
        "acquisition_time_s": summary.acquisition_time_s,
        "fps": summary.fps_mean,
        "proc_ms_p95": summary.proc_ms_p95,
        "proc_ms_mean": summary.proc_ms_mean,
        "wall_time_ms": total_wall_ms,
        "prob_cv": float(np.mean(cv_probs)) if cv_probs else 0.0,
        "prob_ct": float(np.mean(ct_probs)) if ct_probs else 0.0,
        "prob_rw": float(np.mean(rw_probs)) if rw_probs else 0.0,
        "flow_valid_pct": flow_valid_pct,
        "mean_flow_weight": mean_flow_weight,
        "pf_active_pct": pf_active_pct,
        "pf_reacquired_count": pf_reacquired_count,
    }


def main():
    print("=" * 156)
    print("        ISRO PS 26169 — 4-WAY SCIENTIFIC ABLATION EXPERIMENT (STEP 4)")
    print("  (A) IMM vs (B) IMM + Optical Flow vs (C) IMM + Adaptive OF vs (D) IMM + Adaptive OF + Particle Filter")
    print("=" * 156)

    rows = []
    for cond in CONDITIONS:
        print(f"Running scenario: {cond['name']:<35} ...", end="", flush=True)
        res_imm = run_condition(cond, tracker_mode="imm", seed=42)
        res_of_fix = run_condition(cond, tracker_mode="imm_of_fixed", seed=42)
        res_of_adapt = run_condition(cond, tracker_mode="imm_of_adaptive", seed=42)
        res_adapt_pf = run_condition(cond, tracker_mode="imm_of_adaptive_pf", seed=42)
        rows.append((cond["name"], res_imm, res_of_fix, res_of_adapt, res_adapt_pf))
        print(" DONE")

    print("\n" + "=" * 156)
    header = f"{'Condition':<30} | {'Configuration':<20} | {'Mean Err':<8} | {'RMSE':<8} | {'P95':<8} | {'Loss %':<7} | {'Reacq %':<8} | {'Reacq(s)':<9} | {'Lock %':<7} | {'FPS':<6}"
    print(header)
    print("-" * 156)

    for name, imm, fix, adapt, pf in rows:
        reacq_imm_str = f"{imm['reacquisition_time_mean_s']:.2f}" if imm['reacquisition_time_mean_s'] is not None else "-"
        print(
            f"{name:<30} | {'(A) IMM':<20} | {imm['mean_error_px']:<8.2f} | {imm['rmse_error_px']:<8.2f} | {imm['p95_error_px']:<8.2f} | {imm['target_loss_pct']:<7.1f} | {imm['reacquisition_success_pct']:<8.1f} | {reacq_imm_str:<9} | {imm['lock_pct']:<7.1f} | {imm['fps']:<6.1f}"
        )
        reacq_fix_str = f"{fix['reacquisition_time_mean_s']:.2f}" if fix['reacquisition_time_mean_s'] is not None else "-"
        print(
            f"{' ':30} | {'(B) IMM + OF':<20} | {fix['mean_error_px']:<8.2f} | {fix['rmse_error_px']:<8.2f} | {fix['p95_error_px']:<8.2f} | {fix['target_loss_pct']:<7.1f} | {fix['reacquisition_success_pct']:<8.1f} | {reacq_fix_str:<9} | {fix['lock_pct']:<7.1f} | {fix['fps']:<6.1f}"
        )
        reacq_adapt_str = f"{adapt['reacquisition_time_mean_s']:.2f}" if adapt['reacquisition_time_mean_s'] is not None else "-"
        print(
            f"{' ':30} | {'(C) IMM + Adapt OF':<20} | {adapt['mean_error_px']:<8.2f} | {adapt['rmse_error_px']:<8.2f} | {adapt['p95_error_px']:<8.2f} | {adapt['target_loss_pct']:<7.1f} | {adapt['reacquisition_success_pct']:<8.1f} | {reacq_adapt_str:<9} | {adapt['lock_pct']:<7.1f} | {adapt['fps']:<6.1f}"
        )
        reacq_pf_str = f"{pf['reacquisition_time_mean_s']:.2f}" if pf['reacquisition_time_mean_s'] is not None else "-"
        print(
            f"{' ':30} | {'(D) IMM+AdaptOF+PF':<20} | {pf['mean_error_px']:<8.2f} | {pf['rmse_error_px']:<8.2f} | {pf['p95_error_px']:<8.2f} | {pf['target_loss_pct']:<7.1f} | {pf['reacquisition_success_pct']:<8.1f} | {reacq_pf_str:<9} | {pf['lock_pct']:<7.1f} | {pf['fps']:<6.1f}"
        )
        print("-" * 156)

    # Save JSON report
    out_path = Path("ablation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([
            {
                "condition": name,
                "imm": imm,
                "imm_optical_flow_fixed": fix,
                "imm_optical_flow_adaptive": adapt,
                "imm_optical_flow_adaptive_pf": pf,
            }
            for name, imm, fix, adapt, pf in rows
        ], f, indent=2)
    print(f"\n[Ablation] Complete JSON results saved to: {out_path.resolve()}\n")


if __name__ == "__main__":
    main()
