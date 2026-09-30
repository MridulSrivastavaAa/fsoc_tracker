"""
Generate a 30-second, 60 FPS synthetic optical beacon test video and ground truth CSV.
Features:
- Total Frames: 1800 (30.0 s @ 60.0 FPS, 640x480 resolution)
- 5 Realistic phases:
  1. Frames 0-360 (0-6s): Clear sky nominal acquisition & orbital curve
  2. Frames 360-720 (6-12s): Atmospheric scintillation, haze & jitter
  3. Frames 720-960 (12-16s): Cloud occlusion outage (beacon disappears for 1.5s to test reacquisition)
  4. Frames 960-1440 (16-24s): Moving platform vibration, wind drift, and decoy glint
  5. Frames 1440-1800 (24-30s): High-speed figure-8 transit & recovery
- Exports:
  - fsoc_test_video_30s_60fps.mp4
  - fsoc_test_video_30s_60fps_truth.csv
"""
import sys
import math
import cv2
import numpy as np
from pathlib import Path

def generate_video():
    fps = 60.0
    duration_s = 30.0
    total_frames = int(fps * duration_s) # 1800 frames
    width, height = 640, 480
    cx_nominal, cy_nominal = width / 2.0, height / 2.0

    output_dir = Path("c:/SIH/final_2/fsoc_tracker/fsoc_tracker/test_videos")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Also save in public folder for direct browser download if needed
    public_dir = Path("c:/SIH/final_2/fsoc_tracker/web/public")
    public_dir.mkdir(parents=True, exist_ok=True)

    video_path = output_dir / "fsoc_test_video_30s_60fps.mp4"
    csv_path = output_dir / "fsoc_test_video_30s_60fps_truth.csv"

    # Use mp4v fourcc
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height), isColor=False)

    truth_rows = ["frame,time_s,truth_x,truth_y,visible,phase"]

    np.random.seed(42)

    # Initial trajectory state
    t_x, t_y = 120.0, 100.0
    vx, vy = 15.0, 12.0

    print(f"Generating {total_frames} frames ({duration_s}s @ {fps} FPS)...")

    for f in range(total_frames):
        t_sec = f / fps
        frame = np.zeros((height, width), dtype=np.uint8)

        # Baseline noise floor (dark sky with thermal sensor noise)
        noise = np.random.normal(12.0, 3.0, (height, width)).astype(np.float32)

        # Ambient background stars (fixed celestial field)
        np.random.seed(1000 + (f % 5)) # subtle star twinkle
        for _ in range(15):
            sx = int((1000 + _ * 37) % width)
            sy = int((500 + _ * 29) % height)
            noise[sy, sx] += np.random.uniform(15, 35)

        # Phase logic and trajectory
        is_visible = True
        phase_name = "Nominal"

        # Trajectory computation based on simulation phases
        if f < 360:  # Phase 1: 0 - 6s (Smooth orbital arc)
            phase_name = "Nominal Orbit"
            angle = (t_sec / 6.0) * math.pi * 0.8
            t_x = cx_nominal + 180.0 * math.cos(angle + 0.5)
            t_y = cy_nominal + 120.0 * math.sin(angle + 0.5)
            beacon_sigma = 2.2
            intensity = 220.0
            jitter_x, jitter_y = 0.0, 0.0

        elif f < 720:  # Phase 2: 6 - 12s (Atmospheric scintillation + turbulence)
            phase_name = "Turbulence & Jitter"
            t_rel = (t_sec - 6.0)
            t_x = cx_nominal + 140.0 * math.cos(t_rel * 1.2)
            t_y = cy_nominal + 90.0 * math.sin(t_rel * 2.4)
            # Scintillation: fluctuating intensity & beam wander
            intensity = 160.0 + 50.0 * math.sin(t_rel * 14.0) + np.random.normal(0, 15)
            beacon_sigma = 2.5 + 0.6 * math.sin(t_rel * 8.0)
            jitter_x = np.random.normal(0, 3.5)
            jitter_y = np.random.normal(0, 3.5)
            # Add haze / background glow
            noise += 15.0

        elif f < 960:  # Phase 3: 12 - 16s (Cloud Occlusion Dropouts)
            phase_name = "Cloud Occlusion"
            t_rel = (t_sec - 12.0)
            t_x = cx_nominal + 110.0 * math.cos(t_rel * 1.5)
            t_y = cy_nominal + 80.0 * math.sin(t_rel * 1.5)
            jitter_x, jitter_y = 0.0, 0.0
            beacon_sigma = 2.2
            intensity = 200.0
            # Cloud passing: hide beacon between 13.0s and 14.5s (f=780 to 870)
            if 780 <= f <= 870:
                is_visible = False
                intensity = 0.0
                # Cloud diffuse scattering mask
                cloud_val = 40.0 + 20.0 * math.sin((f - 780) / 90.0 * math.pi)
                noise += cloud_val

        elif f < 1440:  # Phase 4: 16 - 24s (Platform Vibration & Decoy Glint)
            phase_name = "Vibration & Decoy"
            t_rel = (t_sec - 16.0)
            t_x = cx_nominal + 160.0 * math.cos(t_rel * 1.1)
            t_y = cy_nominal + 110.0 * math.sin(t_rel * 0.9)
            # High frequency 10 Hz vibration
            jitter_x = 6.0 * math.sin(t_rel * 20.0 * math.pi) + np.random.normal(0, 2)
            jitter_y = 5.0 * math.cos(t_rel * 20.0 * math.pi) + np.random.normal(0, 2)
            intensity = 210.0
            beacon_sigma = 2.4

            # Add decoy glint (sun reflection / hot pixel artifact)
            decoy_x = int(cx_nominal + 70.0 + 20.0 * math.sin(t_rel * 2))
            decoy_y = int(cy_nominal - 60.0 + 15.0 * math.cos(t_rel * 2))
            if 0 <= decoy_x < width and 0 <= decoy_y < height:
                cv2.circle(noise, (decoy_x, decoy_y), 4, 175.0, -1)

        else:  # Phase 5: 24 - 30s (High-speed Figure-8 Re-lock)
            phase_name = "Fast Figure-8 Transit"
            t_rel = (t_sec - 24.0)
            # Lemniscate of Bernoulli
            scale = 190.0
            denom = 1.0 + math.sin(t_rel * 1.6) ** 2
            t_x = cx_nominal + (scale * math.cos(t_rel * 1.6)) / denom
            t_y = cy_nominal + (scale * math.sin(t_rel * 1.6) * math.cos(t_rel * 1.6)) / denom
            jitter_x, jitter_y = np.random.normal(0, 1.2), np.random.normal(0, 1.2)
            intensity = 240.0
            beacon_sigma = 2.0

        # Apply jitter
        eff_x = t_x + jitter_x
        eff_y = t_y + jitter_y

        # Render beacon if visible
        if is_visible and (0 <= eff_x < width) and (0 <= eff_y < height):
            ksize = int(math.ceil(beacon_sigma * 6)) // 2 * 2 + 1
            k = cv2.getGaussianKernel(ksize, beacon_sigma)
            k_norm = k / np.max(k)
            kernel = (np.outer(k_norm, k_norm) * intensity).astype(np.float32)

            x0 = int(round(eff_x)) - ksize // 2
            y0 = int(round(eff_y)) - ksize // 2
            x1, y1 = x0 + ksize, y0 + ksize

            # Safe ROI bounding
            rx0, ry0 = max(0, x0), max(0, y0)
            rx1, ry1 = min(width, x1), min(height, y1)
            kx0, ky0 = rx0 - x0, ry0 - y0
            kx1, ky1 = kx0 + (rx1 - rx0), ky0 + (ry1 - ry0)

            if rx1 > rx0 and ry1 > ry0:
                noise[ry0:ry1, rx0:rx1] += kernel[ky0:ky1, kx0:kx1]

        # Clip and convert to uint8
        frame = np.clip(noise, 0, 255).astype(np.uint8)
        writer.write(frame)

        # Save truth CSV row
        truth_x_str = f"{eff_x:.2f}" if is_visible else ""
        truth_y_str = f"{eff_y:.2f}" if is_visible else ""
        truth_rows.append(f"{f},{t_sec:.4f},{truth_x_str},{truth_y_str},{1 if is_visible else 0},{phase_name}")

    writer.release()

    # Write CSV
    with open(csv_path, "w", encoding="utf-8") as f_csv:
        f_csv.write("\n".join(truth_rows))

    # Also copy to public folder for convenience
    try:
        import shutil
        shutil.copyfile(str(video_path), str(public_dir / "fsoc_test_video_30s_60fps.mp4"))
        with open(public_dir / "fsoc_test_video_30s_60fps_truth.csv", "w", encoding="utf-8") as f_pub:
            f_pub.write("\n".join(truth_rows))
    except Exception as e:
        print(f"Note copying to public: {e}")

    print(f"SUCCESS: Video created at {video_path}")
    print(f"SUCCESS: Truth CSV created at {csv_path}")
    print(f"Size: {video_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    generate_video()
