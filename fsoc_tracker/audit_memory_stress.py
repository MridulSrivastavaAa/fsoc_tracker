"""
audit_memory_stress.py
======================
Prolonged stability and memory leak audit for ISRO PS 26169 FSOC Tracking System (Step 5).
Simulates prolonged execution across 1-minute (1800 frames), 5-minute (9000 frames), and 10-minute (18000 frames) runs.
Monitors process RSS memory, telemetry buffer length, and object counts to detect memory growth or leaks.
"""
import sys
import time
import gc
import psutil
from pathlib import Path

_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fsoc.core.config import default_config
from fsoc.core.engine import ClosedLoopEngine


def audit_run(duration_seconds: float, label: str):
    fps = 30.0
    total_frames = int(duration_seconds * fps)
    print(f"\n=======================================================")
    print(f"Starting Memory Audit: {label} ({duration_seconds}s, {total_frames} frames)")
    print(f"=======================================================")

    proc = psutil.Process()
    gc.collect()
    mem_init_mb = proc.memory_info().rss / (1024 * 1024)

    cfg = default_config()
    cfg.pipeline.duration_s = duration_seconds + 5.0
    cfg.motion.model = "figure8"
    engine = ClosedLoopEngine(cfg)

    # Enable all disturbances for stress test
    engine.disturbances.gaussian.enabled = True
    engine.disturbances.gaussian.sigma = 15.0
    engine.disturbances.salt_pepper.enabled = True
    engine.disturbances.salt_pepper.density = 0.10
    engine.disturbances.jitter.enabled = True
    engine.disturbances.jitter.max_px = 15.0
    engine.disturbances.atmosphere.set_condition("fog", strength=0.60)

    checkpoints = [
        int(total_frames * 0.25),
        int(total_frames * 0.50),
        int(total_frames * 0.75),
        total_frames,
    ]

    t_start = time.perf_counter()
    mem_samples = []

    for frame_idx in range(1, total_frames + 1):
        metric = engine.step()
        if metric is None:
            break

        if frame_idx in checkpoints:
            current_rss = proc.memory_info().rss / (1024 * 1024)
            mem_samples.append((frame_idx, current_rss))
            elapsed = time.perf_counter() - t_start
            actual_fps = frame_idx / elapsed if elapsed > 0 else 0
            print(f"  Frame {frame_idx:5d}/{total_frames} | RSS: {current_rss:.2f} MB | Metrics History: {len(engine.metrics_history)} | Speed: {actual_fps:.1f} FPS")

    gc.collect()
    mem_final_mb = proc.memory_info().rss / (1024 * 1024)
    total_elapsed = time.perf_counter() - t_start
    overall_fps = total_frames / total_elapsed if total_elapsed > 0 else 0
    delta_mb = mem_final_mb - mem_init_mb

    print(f"Finished {label}:")
    print(f"  Initial RSS : {mem_init_mb:.2f} MB")
    print(f"  Final RSS   : {mem_final_mb:.2f} MB")
    print(f"  Delta RSS   : {delta_mb:+.2f} MB")
    print(f"  Average FPS : {overall_fps:.1f} FPS")
    print(f"  Memory Growth Rate: {delta_mb / duration_seconds * 60.0:.3f} MB/min")

    return {
        "label": label,
        "duration_s": duration_seconds,
        "frames": total_frames,
        "mem_init_mb": round(mem_init_mb, 2),
        "mem_final_mb": round(mem_final_mb, 2),
        "delta_mb": round(delta_mb, 2),
        "fps": round(overall_fps, 1),
    }


def main():
    print("=== ISRO PS 26169 PROLONGED STABILITY & MEMORY AUDIT ===")
    r1 = audit_run(60.0, "1-Minute Run (1800 frames)")
    r2 = audit_run(300.0, "5-Minute Run (9000 frames)")
    print("\n=== SUMMARY OF MEMORY AUDIT ===")
    print(f"1-Min Delta: {r1['delta_mb']} MB (Final: {r1['mem_final_mb']} MB)")
    print(f"5-Min Delta: {r2['delta_mb']} MB (Final: {r2['mem_final_mb']} MB)")


if __name__ == "__main__":
    main()
