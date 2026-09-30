"""
generate_multi_tier_videos.py
=============================
Generates 5 benchmark test videos spanning 5 distinct environmental quality levels:
  - Tier 1: 90% Clean (Pristine Deep Space / High-Altitude Clear Sky)
  - Tier 2: 70% Clean (Mild Turbulence & Light Haze)
  - Tier 3: 50% Clean (Moderate Turbulence & Passing Cloud Outage)
  - Tier 4: 30% Clean (Heavy Haze, Strong Turbulence & Decoy Glint)
  - Tier 5: 10% Clean (Severe Storm, Dense Fog, Heavy Jitter & Deep Fading)

Each video is 20 seconds @ 60 FPS (1200 frames) at 640x480 resolution,
accompanied by a matching Ground Truth CSV.
"""
from pathlib import Path
import math
import cv2
import numpy as np
import shutil

OUTPUT_DIR = Path("test_videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WEB_PUBLIC_DIR = Path("../web/public/test_videos")
WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

TIERS = [
    {
        "id": "tier1_clean_90pct",
        "name": "Tier 1 — 90% Clean (Pristine Clear Sky)",
        "duration_s": 20.0,
        "fps": 60.0,
        "width": 640,
        "height": 480,
        "base_noise_mean": 8.0,
        "base_noise_std": 2.0,
        "stars_count": 5,
        "spot_intensity": 250.0,
        "spot_sigma": 2.0,
        "scintillation_amp": 0.05,
        "wander_std": 0.3,
        "jitter_amp": 0.0,
        "vibration_freq": 0.0,
        "haze_level": 0.0,
        "outages": [], # No dropouts
        "decoys": False,
        "salt_pepper": 0.0,
    },
    {
        "id": "tier2_mild_70pct",
        "name": "Tier 2 — 70% Clean (Mild Turbulence & Light Haze)",
        "duration_s": 20.0,
        "fps": 60.0,
        "width": 640,
        "height": 480,
        "base_noise_mean": 14.0,
        "base_noise_std": 4.0,
        "stars_count": 12,
        "spot_intensity": 210.0,
        "spot_sigma": 2.2,
        "scintillation_amp": 0.15,
        "wander_std": 1.2,
        "jitter_amp": 1.5,
        "vibration_freq": 4.0,
        "haze_level": 5.0,
        "outages": [],
        "decoys": False,
        "salt_pepper": 0.001,
    },
    {
        "id": "tier3_moderate_50pct",
        "name": "Tier 3 — 50% Clean (Moderate Turbulence & Cloud Outage)",
        "duration_s": 20.0,
        "fps": 60.0,
        "width": 640,
        "height": 480,
        "base_noise_mean": 22.0,
        "base_noise_std": 6.5,
        "stars_count": 18,
        "spot_intensity": 160.0,
        "spot_sigma": 2.5,
        "scintillation_amp": 0.30,
        "wander_std": 3.0,
        "jitter_amp": 3.5,
        "vibration_freq": 8.0,
        "haze_level": 15.0,
        "outages": [(7.0, 8.5)], # 1.5s cloud block
        "decoys": False,
        "salt_pepper": 0.005,
    },
    {
        "id": "tier4_degraded_30pct",
        "name": "Tier 4 — 30% Clean (Heavy Haze, Strong Turbulence & Glint)",
        "duration_s": 20.0,
        "fps": 60.0,
        "width": 640,
        "height": 480,
        "base_noise_mean": 32.0,
        "base_noise_std": 10.0,
        "stars_count": 25,
        "spot_intensity": 110.0,
        "spot_sigma": 2.8,
        "scintillation_amp": 0.50,
        "wander_std": 6.0,
        "jitter_amp": 7.0,
        "vibration_freq": 12.0,
        "haze_level": 28.0,
        "outages": [(5.5, 7.0), (12.0, 13.5)], # two 1.5s cloud blocks
        "decoys": True,
        "salt_pepper": 0.015,
    },
    {
        "id": "tier5_extreme_10pct",
        "name": "Tier 5 — 10% Clean (Severe Storm, Fog & Deep Fading)",
        "duration_s": 20.0,
        "fps": 60.0,
        "width": 640,
        "height": 480,
        "base_noise_mean": 48.0,
        "base_noise_std": 16.0,
        "stars_count": 35,
        "spot_intensity": 65.0, # dim spot
        "spot_sigma": 3.2,
        "scintillation_amp": 0.70,
        "wander_std": 12.0,
        "jitter_amp": 14.0,
        "vibration_freq": 16.0,
        "haze_level": 50.0,
        "outages": [(4.0, 6.0), (9.0, 11.0), (14.5, 16.5)], # multiple heavy dropouts
        "decoys": True,
        "salt_pepper": 0.04,
    },
]

def render_tier_video(tier_cfg: dict):
    vid_id = tier_cfg["id"]
    name = tier_cfg["name"]
    duration_s = tier_cfg["duration_s"]
    fps = tier_cfg["fps"]
    width = tier_cfg["width"]
    height = tier_cfg["height"]
    total_frames = int(duration_s * fps)

    video_path = OUTPUT_DIR / f"{vid_id}.mp4"
    csv_path = OUTPUT_DIR / f"{vid_id}_truth.csv"

    print(f"\n--- Generating {name} ---")
    print(f"File: {video_path} ({total_frames} frames)")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height), isColor=False)

    truth_rows = ["frame,time_s,truth_x,truth_y,visible,phase"]

    np.random.seed(101)
    cx_nominal, cy_nominal = width / 2.0, height / 2.0

    for f in range(total_frames):
        t_sec = f / fps
        noise = np.random.normal(tier_cfg["base_noise_mean"], tier_cfg["base_noise_std"], (height, width)).astype(np.float32)

        # Ambient celestial stars
        np.random.seed(500 + (f % 7))
        for s_idx in range(tier_cfg["stars_count"]):
            sx = int((400 + s_idx * 47) % width)
            sy = int((200 + s_idx * 31) % height)
            noise[sy, sx] += np.random.uniform(10, 30)

        # Haze background glow
        if tier_cfg["haze_level"] > 0:
            noise += tier_cfg["haze_level"]

        # Salt and pepper noise
        if tier_cfg["salt_pepper"] > 0:
            sp_mask = np.random.uniform(0, 1, (height, width)) < tier_cfg["salt_pepper"]
            noise[sp_mask] = np.random.uniform(180, 255, np.count_nonzero(sp_mask))

        # Check cloud outages
        is_visible = True
        phase_str = "Clear Track"
        for o_start, o_end in tier_cfg["outages"]:
            if o_start <= t_sec <= o_end:
                is_visible = False
                phase_str = "Cloud Outage"
                # Cloud scattering fog mask
                cloud_noise = 30.0 + 15.0 * math.sin((t_sec - o_start) / (o_end - o_start) * math.pi)
                noise += cloud_noise
                break

        # Nominal trajectory (Smooth Figure-8 Orbital Pass)
        scale = 160.0
        omega = 0.8
        denom = 1.0 + math.sin(t_sec * omega) ** 2
        t_x = cx_nominal + (scale * math.cos(t_sec * omega)) / denom
        t_y = cy_nominal + (scale * math.sin(t_sec * omega) * math.cos(t_sec * omega)) / denom

        # Atmospheric Beam Wander
        wander_x = np.random.normal(0, tier_cfg["wander_std"])
        wander_y = np.random.normal(0, tier_cfg["wander_std"])

        # Sensor Jitter & Platform Vibration
        jitter_x = 0.0
        jitter_y = 0.0
        if tier_cfg["vibration_freq"] > 0:
            jitter_x = tier_cfg["jitter_amp"] * math.sin(t_sec * 2.0 * math.pi * tier_cfg["vibration_freq"])
            jitter_y = tier_cfg["jitter_amp"] * math.cos(t_sec * 2.0 * math.pi * tier_cfg["vibration_freq"])

        eff_x = t_x + wander_x + jitter_x
        eff_y = t_y + wander_y + jitter_y

        # Atmospheric Scintillation (Intensity Fluctuations)
        scint = 1.0 + tier_cfg["scintillation_amp"] * math.sin(t_sec * 18.0) + np.random.normal(0, tier_cfg["scintillation_amp"] * 0.3)
        cur_intensity = max(10.0, tier_cfg["spot_intensity"] * scint)

        # Render Decoy spot if enabled
        if tier_cfg["decoys"]:
            decoy_x = int(cx_nominal - 80.0 + 25.0 * math.sin(t_sec * 1.5))
            decoy_y = int(cy_nominal + 60.0 + 20.0 * math.cos(t_sec * 1.5))
            if 0 <= decoy_x < width and 0 <= decoy_y < height:
                cv2.circle(noise, (decoy_x, decoy_y), 4, 150.0, -1)

        # Render Gaussian Laser Beacon
        if is_visible and (0 <= eff_x < width) and (0 <= eff_y < height):
            b_sigma = tier_cfg["spot_sigma"]
            ksize = int(math.ceil(b_sigma * 6)) // 2 * 2 + 1
            k = cv2.getGaussianKernel(ksize, b_sigma)
            k_norm = k / np.max(k)
            kernel = (np.outer(k_norm, k_norm) * cur_intensity).astype(np.float32)

            x0 = int(round(eff_x)) - ksize // 2
            y0 = int(round(eff_y)) - ksize // 2
            x1, y1 = x0 + ksize, y0 + ksize

            rx0, ry0 = max(0, x0), max(0, y0)
            rx1, ry1 = min(width, x1), min(height, y1)
            kx0, ky0 = rx0 - x0, ry0 - y0
            kx1, ky1 = kx0 + (rx1 - rx0), ky0 + (ry1 - ry0)

            if rx1 > rx0 and ry1 > ry0:
                noise[ry0:ry1, rx0:rx1] += kernel[ky0:ky1, kx0:kx1]

        # Clip frame
        frame = np.clip(noise, 0, 255).astype(np.uint8)
        writer.write(frame)

        # Record CSV row
        tx_s = f"{eff_x:.2f}" if is_visible else ""
        ty_s = f"{eff_y:.2f}" if is_visible else ""
        truth_rows.append(f"{f},{t_sec:.4f},{tx_s},{ty_s},{1 if is_visible else 0},{phase_str}")

    writer.release()

    with open(csv_path, "w", encoding="utf-8") as f_csv:
        f_csv.write("\n".join(truth_rows))

    try:
        shutil.copyfile(str(video_path), str(WEB_PUBLIC_DIR / f"{vid_id}.mp4"))
        with open(WEB_PUBLIC_DIR / f"{vid_id}_truth.csv", "w", encoding="utf-8") as f_pub:
            f_pub.write("\n".join(truth_rows))
    except Exception as e:
        print(f"Public sync notice: {e}")

    print(f"Saved: {video_path} ({video_path.stat().st_size / 1024:.1f} KB)")
    print(f"Saved: {csv_path}")

def main():
    print("==========================================================")
    print("Generating 5 Multi-Tier Environmental Quality Benchmark Videos")
    print("==========================================================")
    for tier in TIERS:
        render_tier_video(tier)
    print("\nAll 5 videos generated successfully!")

if __name__ == "__main__":
    main()
