"""
generate_decoy_benchmark_videos.py
==================================
Generates 5 High-Fidelity 10-Second @ 60 FPS Benchmark Test Videos (600 frames each)
incorporating Decoy Glints, Solar Flare Reflections, and Optical Disturbances
ranging from Clear to Hard-Visible (Severe Atmospheric Turbulence & Deep Signal Fade).

Output directories:
- test_videos/
- benchmark_results/test_videos/
- ../web/public/test_videos/ (if exists)

Videos generated:
1. 01_clear_sky_decoy_10s.mp4 (Level 1: Clear Sky with Crossing Decoy Glint)
2. 02_haze_moving_glint_10s.mp4 (Level 2: Atmospheric Haze with Drifting & Pulsing Glint)
3. 03_dense_fog_glint_10s.mp4 (Level 3: Dense Fog with Intermittent Solar Flares)
4. 04_rain_streaks_decoys_10s.mp4 (Level 4: Heavy Rain Streaks with Multi-Decoy Cluster)
5. 05_hard_turbulence_deep_fade_10s.mp4 (Level 5: Hard Visible — Deep Scintillation Fade & Decoy)

Each video includes an accompanying ground-truth CSV with exact pixel coordinates.
"""
from __future__ import annotations
import argparse
import math
import csv
import shutil
from pathlib import Path
import numpy as np
import cv2


def render_gaussian_spot(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    radius: float = 5.0,
    peak_intensity: float = 230.0,
) -> None:
    """Render a diffraction-limited Gaussian beacon spot onto a float32 canvas."""
    H, W = canvas.shape[:2]
    ix, iy = int(round(cx)), int(round(cy))
    r_int = int(math.ceil(radius * 3.5))

    x0 = max(0, ix - r_int)
    x1 = min(W, ix + r_int + 1)
    y0 = max(0, iy - r_int)
    y1 = min(H, iy + r_int + 1)

    if x0 >= x1 or y0 >= y1:
        return

    ys, xs = np.ogrid[y0:y1, x0:x1]
    dist_sq = (xs - cx) ** 2 + (ys - cy) ** 2
    spot = peak_intensity * np.exp(-0.5 * dist_sq / (radius ** 2))
    canvas[y0:y1, x0:x1] = np.maximum(canvas[y0:y1, x0:x1], spot)


def add_rain_streaks(canvas: np.ndarray, rng: np.random.Generator, n_streaks: int = 85) -> None:
    """Overlay realistic diagonal rain streaks."""
    H, W = canvas.shape[:2]
    for _ in range(n_streaks):
        x = int(rng.integers(0, W))
        y = int(rng.integers(0, H))
        length = int(rng.integers(12, 28))
        brightness = float(rng.uniform(140, 220))
        for k in range(length):
            sx = x + k // 3
            sy = y + k
            if 0 <= sx < W and 0 <= sy < H:
                canvas[sy, sx] = max(canvas[sy, sx], brightness)


def generate_benchmark_suite(
    output_dirs: list[Path],
    width: int = 640,
    height: int = 480,
    duration_s: float = 10.0,
    fps: float = 60.0,
) -> list[dict]:
    primary_dir = output_dirs[0]
    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)

    total_frames = int(round(duration_s * fps))  # 600 frames for 10s @ 60fps
    dt = 1.0 / fps

    print(f"\n================================================================================")
    print(f"[Video Generator] Generating 5 Benchmark Test Videos ({duration_s}s @ {fps} FPS = {total_frames} frames each)")
    print(f"[Video Generator] Target Primary Output: {primary_dir.resolve()}")
    print(f"================================================================================\n")

    configs = [
        {
            "id": 1,
            "filename_10s": "01_clear_sky_decoy_10s.mp4",
            "filename_compat": "01_clear_sky_decoy_glint.mp4",
            "name": "Level 1: Clear Sky with Crossing Decoy Glint",
            "desc": "Baseline high-contrast optical feed. True beacon intersects a secondary moving decoy glint.",
            "atmo_alpha": 1.0,
            "atmo_beta": 0.0,
            "fog_blur": 0.0,
            "rain": False,
            "noise_sigma": 2.5,
            "sp_density": 0.003,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "crossing",
        },
        {
            "id": 2,
            "filename_10s": "02_haze_moving_glint_10s.mp4",
            "filename_compat": "02_haze_moving_glint.mp4",
            "name": "Level 2: Atmospheric Haze with Drifting Glint",
            "desc": "Moderate contrast degradation with a persistent drifting and pulsing decoy glint.",
            "atmo_alpha": 0.72,
            "atmo_beta": 18.0,
            "fog_blur": 0.6,
            "rain": False,
            "noise_sigma": 6.0,
            "sp_density": 0.015,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "drifting",
        },
        {
            "id": 3,
            "filename_10s": "03_dense_fog_glint_10s.mp4",
            "filename_compat": "03_dense_fog_flickering_glint.mp4",
            "name": "Level 3: Dense Fog with Intermittent Solar Glints",
            "desc": "Severe contrast loss, Mie scattering halo, and random specular glint flashes.",
            "atmo_alpha": 0.40,
            "atmo_beta": 42.0,
            "fog_blur": 1.8,
            "rain": False,
            "noise_sigma": 10.0,
            "sp_density": 0.035,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "flashing",
        },
        {
            "id": 4,
            "filename_10s": "04_rain_streaks_decoys_10s.mp4",
            "filename_compat": "04_rain_streaks_multiple_decoys.mp4",
            "name": "Level 4: Heavy Rain Streaks with Multi-Decoy Cluster",
            "desc": "High dynamic noise, diagonal rain streaks, and two simultaneous false target spots.",
            "atmo_alpha": 0.76,
            "atmo_beta": 10.0,
            "fog_blur": 0.0,
            "rain": True,
            "noise_sigma": 12.0,
            "sp_density": 0.06,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "multi",
        },
        {
            "id": 5,
            "filename_10s": "05_hard_turbulence_deep_fade_10s.mp4",
            "filename_compat": "05_hard_turbulence_deep_fade_glint.mp4",
            "name": "Level 5: Hard Visible — Deep Scintillation Fade & Decoy",
            "desc": "Kolmogorov turbulence, beam wander, and deep signal fade (beacon drops to 15%) while decoy stays bright.",
            "atmo_alpha": 0.58,
            "atmo_beta": 16.0,
            "fog_blur": 0.8,
            "rain": False,
            "noise_sigma": 15.0,
            "sp_density": 0.05,
            "scintillation": True,
            "deep_fade": True,
            "decoy_mode": "persistent_during_fade",
        },
    ]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    generated_summary = []

    for cfg in configs:
        vid_filename = cfg["filename_10s"]
        csv_filename = vid_filename.replace(".mp4", "_gt.csv")
        vid_path = primary_dir / vid_filename
        csv_path = primary_dir / csv_filename

        # Write 3-channel BGR video for universal playback across browsers, VLC, and Windows Media Player
        writer = cv2.VideoWriter(str(vid_path), fourcc, fps, (width, height), isColor=True)

        rng = np.random.default_rng(seed=100 + cfg["id"] * 37)

        print(f"[Video {cfg['id']}/5] Rendering '{vid_filename}' ({cfg['name']})...")

        gt_records = []

        # True Beacon Trajectory: Lissajous curve
        # Completes 2 full loops in duration_s
        bx0, by0 = 320.0, 240.0
        r_x, r_y = 180.0, 110.0
        omega_b = 2.0 * math.pi / (duration_s / 2.0)

        # Decoy Trajectory setup
        d_omega = 2.0 * math.pi / (duration_s / 2.5)

        # Deep fade interval: occurs between 35% and 62% of total duration (e.g. 3.5s to 6.2s in 10s video)
        fade_start_s = 0.35 * duration_s
        fade_end_s = 0.62 * duration_s

        for frame_idx in range(total_frames):
            t = frame_idx * dt

            # 1. Base Dark Canvas with subtle cosmic background (intensity ~15)
            canvas = np.full((height, width), 15.0, dtype=np.float32)

            # 2. True Beacon Coordinates
            bx = bx0 + r_x * math.sin(omega_b * t)
            by = by0 + r_y * math.sin(2.0 * omega_b * t + 0.5)

            # Intensity modulation / Scintillation
            beacon_intensity = 238.0
            if cfg["scintillation"]:
                scint_factor = math.exp(rng.normal(0.0, 0.22))
                beacon_intensity = float(np.clip(beacon_intensity * scint_factor, 30.0, 255.0))

            # Deep Fade events for Video 5
            beacon_visible = True
            if cfg["deep_fade"]:
                if fade_start_s <= t <= fade_end_s:
                    beacon_intensity = 25.0  # drop below detection threshold
                    beacon_visible = False

            # Beam wander optical displacement
            if cfg["scintillation"]:
                bx += float(rng.normal(0.0, 1.2))
                by += float(rng.normal(0.0, 1.2))

            # Render True Beacon
            render_gaussian_spot(canvas, bx, by, radius=2.2, peak_intensity=beacon_intensity)

            # 3. Decoy Glint Coordinates & Rendering
            decoy_x: float | None = None
            decoy_y: float | None = None
            decoy_intensity: float = 0.0

            if cfg["decoy_mode"] == "crossing":
                # Decoy crosses path from bottom-left to top-right
                progress = t / duration_s
                decoy_x = 110.0 + (width - 220.0) * progress
                decoy_y = 380.0 - (height - 200.0) * progress
                decoy_intensity = 222.0
                render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.0, peak_intensity=decoy_intensity)

            elif cfg["decoy_mode"] == "drifting":
                # Decoy orbits nearby with slow drift and brightness oscillation
                decoy_x = 320.0 + 130.0 * math.cos(d_omega * t)
                decoy_y = 240.0 + 80.0 * math.sin(d_omega * t)
                decoy_intensity = float(210.0 + 36.0 * math.sin(3.5 * t))
                render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.0, peak_intensity=decoy_intensity)

            elif cfg["decoy_mode"] == "flashing":
                # Decoy flashes brightly for 0.7s every 2.8s
                flash_cycle = t % 2.8
                if flash_cycle < 0.7:
                    decoy_x = 230.0 + 70.0 * math.sin(1.2 * t)
                    decoy_y = 170.0 + 50.0 * math.cos(1.2 * t)
                    decoy_intensity = 250.0  # very bright flare
                    render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.8, peak_intensity=decoy_intensity)
                else:
                    decoy_x, decoy_y = None, None
                    decoy_intensity = 0.0

            elif cfg["decoy_mode"] == "multi":
                # Two simultaneous decoy glints
                d1_x = 180.0 + 80.0 * math.sin(1.6 * t)
                d1_y = 140.0 + 60.0 * math.cos(1.6 * t)
                d2_x = 440.0 + 90.0 * math.cos(2.1 * t)
                d2_y = 320.0 + 50.0 * math.sin(2.1 * t)
                render_gaussian_spot(canvas, d1_x, d1_y, radius=1.9, peak_intensity=218.0)
                render_gaussian_spot(canvas, d2_x, d2_y, radius=1.8, peak_intensity=208.0)
                decoy_x, decoy_y = d1_x, d1_y
                decoy_intensity = 218.0

            elif cfg["decoy_mode"] == "persistent_during_fade":
                # Decoy remains clearly visible at 230 intensity, especially during beacon deep fade
                decoy_x = 360.0 + 135.0 * math.cos(d_omega * t)
                decoy_y = 220.0 + 75.0 * math.sin(d_omega * t)
                decoy_intensity = 230.0
                render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.1, peak_intensity=decoy_intensity)

            # 4. Atmospheric Degradation (Linear contrast + brightness)
            canvas = canvas * cfg["atmo_alpha"] + cfg["atmo_beta"]

            # Fog blurring
            if cfg["fog_blur"] > 0.0:
                ks = max(3, int(6 * cfg["fog_blur"] + 1) | 1)
                canvas = cv2.GaussianBlur(canvas, (ks, ks), cfg["fog_blur"])

            # Rain Streaks
            if cfg["rain"]:
                add_rain_streaks(canvas, rng, n_streaks=85)

            # 5. Gaussian & Salt/Pepper Sensor Noise
            if cfg["noise_sigma"] > 0.0:
                noise = rng.normal(0.0, cfg["noise_sigma"], (height, width)).astype(np.float32)
                canvas += noise

            canvas_uint8 = np.clip(canvas, 0, 255).astype(np.uint8)

            if cfg["sp_density"] > 0.0:
                n_sp = int(width * height * cfg["sp_density"])
                ys = rng.integers(0, height, n_sp // 2)
                xs = rng.integers(0, width, n_sp // 2)
                canvas_uint8[ys, xs] = 255
                ys_p = rng.integers(0, height, n_sp // 2)
                xs_p = rng.integers(0, width, n_sp // 2)
                canvas_uint8[ys_p, xs_p] = 0

            # Convert to 3-channel BGR
            frame_bgr = cv2.cvtColor(canvas_uint8, cv2.COLOR_GRAY2BGR)

            # Write Frame to Video
            writer.write(frame_bgr)

            # Record Ground Truth CSV
            gt_records.append([
                frame_idx,
                round(t, 4),
                round(bx, 2),
                round(by, 2),
                1 if beacon_visible else 0,
                round(beacon_intensity, 1),
                round(decoy_x, 2) if decoy_x is not None else "",
                round(decoy_y, 2) if decoy_y is not None else "",
                round(decoy_intensity, 1),
            ])

        writer.release()

        # Write Ground Truth CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow([
                "frame_idx", "timestamp_s", "beacon_x", "beacon_y",
                "beacon_visible", "beacon_intensity", "decoy_x", "decoy_y", "decoy_intensity"
            ])
            csv_writer.writerows(gt_records)

        size_mb = vid_path.stat().st_size / (1024 * 1024)
        print(f" -> Generated: {vid_path.name} ({size_mb:.2f} MB, {total_frames} frames, GT CSV saved)")

        # Sync to all extra output directories & save compatibility aliases
        for extra_dir in output_dirs[1:]:
            try:
                dest_vid = extra_dir / vid_filename
                dest_csv = extra_dir / csv_filename
                shutil.copy2(str(vid_path), str(dest_vid))
                shutil.copy2(str(csv_path), str(dest_csv))
            except Exception as e:
                print(f"   [Notice] Sync to {extra_dir} error: {e}")

        # Also create compatibility aliases (e.g. 01_clear_sky_decoy_glint.mp4)
        compat_vid_name = cfg["filename_compat"]
        compat_csv_name = compat_vid_name.replace(".mp4", "_gt.csv")
        for d in output_dirs:
            try:
                shutil.copy2(str(vid_path), str(d / compat_vid_name))
                shutil.copy2(str(csv_path), str(d / compat_csv_name))
            except Exception:
                pass

        generated_summary.append({
            "id": cfg["id"],
            "filename": vid_filename,
            "compat_name": compat_vid_name,
            "name": cfg["name"],
            "size_mb": round(size_mb, 2),
            "frames": total_frames,
            "duration_s": duration_s,
            "fps": fps,
        })

    print(f"\n================================================================================")
    print(f"[SUCCESS] All 5 Benchmark Test Videos (10s @ 60 FPS) Generated Successfully!")
    print(f"================================================================================\n")
    return generated_summary


def main():
    parser = argparse.ArgumentParser(description="Generate 5 Decoy Glint Benchmark Videos")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds (default: 10.0)")
    parser.add_argument("--fps", type=float, default=60.0, help="Frames per second (default: 60.0)")
    parser.add_argument("--width", type=int, default=640, help="Video width in pixels (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Video height in pixels (default: 480)")
    parser.add_argument("--output-dir", type=str, default="test_videos", help="Primary output directory")
    args = parser.parse_args()

    # Define target directories
    script_dir = Path(__file__).resolve().parent
    primary_out = script_dir / args.output_dir
    benchmarks_out = script_dir / "benchmark_results" / "test_videos"
    web_public_out = script_dir.parent / "web" / "public" / "test_videos"
    root_test_videos = script_dir.parent / "test_videos"

    output_dirs = [primary_out, benchmarks_out, root_test_videos]
    if web_public_out.parent.exists():
        output_dirs.append(web_public_out)

    generate_benchmark_suite(
        output_dirs=output_dirs,
        width=args.width,
        height=args.height,
        duration_s=args.duration,
        fps=args.fps,
    )


if __name__ == "__main__":
    main()
