"""
generate_decoy_benchmark_videos.py
==================================
Generates 5 High-Fidelity 30-Second @ 60 FPS Benchmark-2 Test Videos
incorporating Decoy Glints, Solar Flare Reflections, and Optical Disturbances
ranging from Clear to Hard-Visible (Severe Atmospheric Turbulence & Deep Fade).

Output directory: benchmark_results/test_videos/
Videos generated:
1. 01_clear_sky_decoy_glint.mp4 (1800 frames @ 60 FPS)
2. 02_haze_moving_glint.mp4 (1800 frames @ 60 FPS)
3. 03_dense_fog_flickering_glint.mp4 (1800 frames @ 60 FPS)
4. 04_rain_streaks_multiple_decoys.mp4 (1800 frames @ 60 FPS)
5. 05_hard_turbulence_deep_fade_glint.mp4 (1800 frames @ 60 FPS)

Each video includes an accompanying ground-truth CSV with exact pixel coordinates.
"""
from __future__ import annotations
import math
import csv
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
    r_int = int(math.ceil(radius * 3.0))

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


def add_rain_streaks(canvas: np.ndarray, rng: np.random.Generator, n_streaks: int = 70) -> None:
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
    output_dir: Path,
    width: int = 640,
    height: int = 480,
    duration_s: float = 30.0,
    fps: float = 60.0,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total_frames = int(round(duration_s * fps))  # 1800 frames
    dt = 1.0 / fps

    print(f"[Video Generator] Generating 5 Benchmark-2 Test Videos ({duration_s}s @ {fps} FPS = {total_frames} frames each)...")
    print(f"[Video Generator] Output directory: {output_dir.resolve()}")

    configs = [
        {
            "id": 1,
            "filename": "01_clear_sky_decoy_glint.mp4",
            "name": "Level 1: Clear Sky with Crossing Decoy Glint",
            "desc": "Baseline high-contrast optical feed. True beacon intersects a secondary moving decoy glint.",
            "atmo_alpha": 1.0,
            "atmo_beta": 0.0,
            "fog_blur": 0.0,
            "rain": False,
            "noise_sigma": 3.0,
            "sp_density": 0.005,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "crossing",
        },
        {
            "id": 2,
            "filename": "02_haze_moving_glint.mp4",
            "name": "Level 2: Atmospheric Haze with Drifting Glint",
            "desc": "Moderate contrast degradation with a persistent drifting decoy glint.",
            "atmo_alpha": 0.72,
            "atmo_beta": 18.0,
            "fog_blur": 0.6,
            "rain": False,
            "noise_sigma": 7.0,
            "sp_density": 0.02,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "drifting",
        },
        {
            "id": 3,
            "filename": "03_dense_fog_flickering_glint.mp4",
            "name": "Level 3: Dense Fog with Intermittent Solar Glints",
            "desc": "Severe contrast loss, Mie scattering halo, and random specular glint flashes.",
            "atmo_alpha": 0.42,
            "atmo_beta": 40.0,
            "fog_blur": 1.8,
            "rain": False,
            "noise_sigma": 11.0,
            "sp_density": 0.04,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "flashing",
        },
        {
            "id": 4,
            "filename": "04_rain_streaks_multiple_decoys.mp4",
            "name": "Level 4: Heavy Rain Streaks with Multi-Decoy Cluster",
            "desc": "High dynamic noise, diagonal rain streaks, and two simultaneous false target spots.",
            "atmo_alpha": 0.78,
            "atmo_beta": 8.0,
            "fog_blur": 0.0,
            "rain": True,
            "noise_sigma": 12.0,
            "sp_density": 0.08,
            "scintillation": False,
            "deep_fade": False,
            "decoy_mode": "multi",
        },
        {
            "id": 5,
            "filename": "05_hard_turbulence_deep_fade_glint.mp4",
            "name": "Level 5: Hard Visible — Deep Scintillation Fade & Decoy",
            "desc": "Kolmogorov turbulence, beam wander, and two deep signal fades (beacon drops to 15%) while decoy stays bright.",
            "atmo_alpha": 0.60,
            "atmo_beta": 15.0,
            "fog_blur": 0.8,
            "rain": False,
            "noise_sigma": 16.0,
            "sp_density": 0.06,
            "scintillation": True,
            "deep_fade": True,
            "decoy_mode": "persistent_during_fade",
        },
    ]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    for cfg in configs:
        vid_path = output_dir / cfg["filename"]
        csv_path = output_dir / cfg["filename"].replace(".mp4", "_gt.csv")
        writer = cv2.VideoWriter(str(vid_path), fourcc, fps, (width, height), isColor=False)

        rng = np.random.default_rng(seed=100 + cfg["id"] * 37)

        print(f"\n[Video {cfg['id']}/5] Rendering '{cfg['filename']}' ({cfg['name']})...")

        gt_records = []

        # True Beacon Trajectory: Lissajous / smooth curve
        # Starts at (140, 160) and sweeps smoothly across the viewport
        bx0, by0 = 320.0, 240.0
        r_x, r_y = 180.0, 110.0
        omega_b = 2.0 * math.pi / 15.0  # 15s period for two full loops in 30s

        # Decoy Trajectory Setup
        # Depending on mode, decoy moves differently
        d_omega = 2.0 * math.pi / 10.0

        for frame_idx in range(total_frames):
            t = frame_idx * dt

            # 1. Base Dark Canvas with subtle cosmic background (intensity ~15)
            canvas = np.full((height, width), 16.0, dtype=np.float32)

            # 2. True Beacon Coordinates
            bx = bx0 + r_x * math.sin(omega_b * t)
            by = by0 + r_y * math.sin(2.0 * omega_b * t + 0.5)

            # Intensity modulation / Scintillation
            beacon_intensity = 235.0
            if cfg["scintillation"]:
                # Log-normal intensity flicker
                scint_factor = math.exp(rng.normal(0.0, 0.25))
                beacon_intensity = np.clip(beacon_intensity * scint_factor, 30.0, 255.0)

            # Deep Fade events for Video 5:
            # Fade 1: between t=8s and t=11s (beacon drops to 15%)
            # Fade 2: between t=20s and t=23s
            beacon_visible = True
            if cfg["deep_fade"]:
                if (8.0 <= t <= 11.0) or (20.0 <= t <= 23.0):
                    beacon_intensity = 28.0  # deep fade below standard threshold
                    beacon_visible = False

            # Beam wander optical displacement
            if cfg["scintillation"]:
                bx += rng.normal(0.0, 1.2)
                by += rng.normal(0.0, 1.2)

            # Render True Beacon
            render_gaussian_spot(canvas, bx, by, radius=2.2, peak_intensity=beacon_intensity)

            # 3. Decoy Glint Coordinates & Rendering
            decoy_x: float | None = None
            decoy_y: float | None = None
            decoy_intensity: float = 0.0

            if cfg["decoy_mode"] == "crossing":
                # Decoy crosses path from bottom-left to top-right
                decoy_x = 100.0 + (width - 200.0) * (t / duration_s)
                decoy_y = 380.0 - (height - 200.0) * (t / duration_s)
                decoy_intensity = 220.0
                render_gaussian_spot(canvas, decoy_x, decoy_y, radius=1.9, peak_intensity=decoy_intensity)

            elif cfg["decoy_mode"] == "drifting":
                # Decoy orbits nearby with slow drift
                decoy_x = 320.0 + 130.0 * math.cos(d_omega * t)
                decoy_y = 240.0 + 80.0 * math.sin(d_omega * t)
                decoy_intensity = 210.0 + 35.0 * math.sin(4.0 * t)  # pulsing brightness
                render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.0, peak_intensity=decoy_intensity)

            elif cfg["decoy_mode"] == "flashing":
                # Decoy flashes brightly for 0.8s every 4 seconds
                flash_cycle = t % 4.0
                if flash_cycle < 0.8:
                    decoy_x = 220.0 + 60.0 * math.sin(t)
                    decoy_y = 160.0 + 40.0 * math.cos(t)
                    decoy_intensity = 250.0  # very bright flare
                    render_gaussian_spot(canvas, decoy_x, decoy_y, radius=2.8, peak_intensity=decoy_intensity)
                else:
                    decoy_x, decoy_y = None, None
                    decoy_intensity = 0.0

            elif cfg["decoy_mode"] == "multi":
                # Two simultaneous decoy glints
                d1_x = 180.0 + 80.0 * math.sin(1.5 * t)
                d1_y = 140.0 + 60.0 * math.cos(1.5 * t)
                d2_x = 440.0 + 90.0 * math.cos(2.0 * t)
                d2_y = 320.0 + 50.0 * math.sin(2.0 * t)
                render_gaussian_spot(canvas, d1_x, d1_y, radius=1.8, peak_intensity=215.0)
                render_gaussian_spot(canvas, d2_x, d2_y, radius=1.7, peak_intensity=205.0)
                decoy_x, decoy_y = d1_x, d1_y
                decoy_intensity = 215.0

            elif cfg["decoy_mode"] == "persistent_during_fade":
                # Decoy remains clearly visible at 220 intensity, especially while beacon fades!
                decoy_x = 360.0 + 140.0 * math.cos(d_omega * t)
                decoy_y = 220.0 + 70.0 * math.sin(d_omega * t)
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

            canvas = np.clip(canvas, 0, 255).astype(np.uint8)

            if cfg["sp_density"] > 0.0:
                n_sp = int(width * height * cfg["sp_density"])
                ys = rng.integers(0, height, n_sp // 2)
                xs = rng.integers(0, width, n_sp // 2)
                canvas[ys, xs] = 255
                ys_p = rng.integers(0, height, n_sp // 2)
                xs_p = rng.integers(0, width, n_sp // 2)
                canvas[ys_p, xs_p] = 0

            # Write Frame to Video
            writer.write(canvas)

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

        # Write CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow([
                "frame_idx", "timestamp_s", "beacon_x", "beacon_y",
                "beacon_visible", "beacon_intensity", "decoy_x", "decoy_y", "decoy_intensity"
            ])
            csv_writer.writerows(gt_records)

        size_mb = vid_path.stat().st_size / (1024 * 1024)
        print(f" -> Generated: {vid_path.name} ({size_mb:.2f} MB, {total_frames} frames, GT CSV saved)")

    print("\n[SUCCESS] All 5 Benchmark-2 Test Videos Generated Successfully!")


if __name__ == "__main__":
    out_dir = Path("benchmark_results") / "test_videos"
    generate_benchmark_suite(out_dir, width=640, height=480, duration_s=30.0, fps=60.0)
