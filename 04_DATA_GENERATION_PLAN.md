# 04 – Data Generation Plan (up to 40 GB)
**Project:** AI-Based Virtual Camera Tracking System for FSOC Coarse Alignment (PS 26169)

## 1. Why we need data, and what for
The simulator can produce unlimited, perfectly labelled data (ground truth is known exactly). We use it to train and validate **three learned components** and to build a benchmark bank:

| # | Component | Task | Data type |
|---|---|---|---|
| D1 | **CNN Verifier** (mandatory AI layer) | beacon / not-beacon on candidate patches + sub-pixel offset regression | 32x32 patches |
| D2 | **Heatmap detector** (optional, stronger AI; also used for wide-area search) | per-pixel beacon probability | viewport frames (640x480) and downscaled full-screen frames (500x500) |
| D3 | **Motion predictor** (optional) | next-position prediction under missing detections | trajectory sequences |
| D4 | **Video benchmark bank** | Benchmark-2 style .mp4 (full screen, 30 fps, noise, beacon) for testing incl. compression artefacts | mp4 + ground-truth CSV |

> Honest note: D1 is a ~7k-parameter CNN and saturates after a few million patches. The 40 GB budget is spent mostly on **diversity and hard negatives**, and it is what makes the bigger D2 model useful. Every component is compared against the classical baseline; we only ship a learned model if it wins.

## 2. Storage Budget (target ≈ 37 GB, hard cap 40 GB)
| Dataset | Unit size | Count | Size |
|---|---|---|---|
| D1 Patches 32x32 uint8 (+ labels) | 1,024 B (+16 B meta) | 16,000,000 | **≈ 16.5 GB** |
| D2a Viewport frames 640x480 uint8 | 307,200 B | 25,000 | **≈ 7.7 GB** |
| D2b Full-screen downscaled 500x500 uint8 | 250,000 B | 16,000 | **≈ 4.0 GB** |
| D3 Trajectory sequences (300 steps x xy float32) | 2,400 B | 400,000 | **≈ 1.0 GB** |
| D4 Train/dev videos (2000x2000, 30 fps, 30 s, H.264 ~40 Mbps) | ~150 MB | 40 | **≈ 6.0 GB** |
| D4 Held-out benchmark videos | ~150 MB | 12 | **≈ 1.8 GB** |
| Manifests, GT CSVs, logs, previews | | | ≈ 0.2 GB |
| **Total** | | | **≈ 37.2 GB** |
| Safety buffer | | | ≈ 2.8 GB |

Disk requirement on the training machine: **>= 60 GB free (SSD)** for data + temp + checkpoints.
A `--budget-gb 40` flag makes the generator scale all counts proportionally and refuse to exceed the cap. A **mini set (~1 GB)** is generated first for quick development loops.

## 3. Generation Method
### 3.1 Principle: domain randomisation
Every sample draws its own scenario from the ranges below. The **same code** used at run time (`simulation/` + `disturbances/`) generates the data, so train and inference distributions match; we then deliberately go a little **beyond** the PS limits so the model is robust at the spec limits.

### 3.2 Parameter ranges
| Parameter | PS spec | Training range |
|---|---|---|
| Target size | 5–20 px | 3–24 px (uniform) |
| Target shape | square default | square 60 %, circle 20 %, cross/diamond 10 %, gaussian spot 10 % |
| Target peak brightness | – | 60–255 (log-uniform) |
| Optical blur (PSF sigma) | – | 0.3–2.5 px |
| Background | – | flat, fractal/Perlin, stars, cloud gradients, vignetting |
| Distractors (static bright blobs, hot pixels, stars) | – | 0–20 per screen, size 2–25 px |
| Salt & Pepper density | ~10 % | 0–12 % |
| Gaussian noise sigma | max 20 | 0–25 |
| Poisson (shot) noise | selectable | on/off, gain 0.3–3 |
| Camera jitter | ±20 px/frame | 0–24 px (uniform + Gaussian) |
| Platform motion | ±20 px/frame | 0–24 px; linear 70 %, circular/random/spiral/fig-8 30 % |
| Atmosphere | clear/haze/fog/rain/low light | all five + mixes; contrast x0.3–1.0, brightness −20 – +50 |
| Turbulence | – | wander 0–10 px, scintillation sigma 0–0.5, blur 0–2 px |
| Compression | (mp4 in benchmark) | JPEG q 40–95 on 30 % of frames; H.264 CRF 18–35 for D4 |
| Target motion | line, circle, fig-8, random (+ spiral, sinusoidal) | all, speed 0–90 % of max slew |

**Severity mix** (sampled per scenario): mild 25 %, moderate 40 %, severe 25 %, beyond-spec 10 %. Each noise type is enabled independently (p = 0.5) so every combination occurs.

### 3.3 D1 – Patches (16 M)
Patches are cut from generated viewport frames (frames are discarded after extraction: ≈ 250 k frames x 64 patches). Patch centre = candidate location as the real detector would produce it (threshold + connected components on the disturbed frame) plus random extra samples.

| Class | Share | Count | Definition |
|---|---|---|---|
| Positive | 37.5 % | 6.0 M | beacon centre within 3 px of patch centre; label also stores true sub-pixel offset (dx, dy) |
| **Hard negative** | 50 % | 8.0 M | noise clusters, S&P clumps, rain streaks, hot pixels, stars, distractor blobs, fog/cloud edges, half-visible beacon (centre > 3 px away), lookalike blobs |
| Easy negative | 12.5 % | 2.0 M | plain background/noise |

Per-sample metadata: `label, dx, dy, snr, size, shape, noise_flags, atmosphere, jitter, scene_seed, split`.
Multi-task target: classification (BCE) + offset regression (Huber, positives only) -> improves centroiding accuracy.

### 3.4 D2 – Frames
- **D2a (25 k)**: 640x480 viewport frames with target mask (Gaussian heatmap, sigma 2 px) and exact centroid. Sampled so the beacon is inside the FOV at random positions (80 %), partially at the border (10 %), absent (10 %, teaches "no target").
- **D2b (16 k)**: full 2000x2000 scene rendered with disturbances then downscaled x4 to 500x500 (target becomes 1.3–5 px). Used for wide-area acquisition training/evaluation.
- Stored uint8; labels: centroid (float32, screen px), heatmap regenerated on the fly (saves space).

### 3.5 D3 – Trajectory sequences (400 k)
300 time steps @30 Hz of: target path (all 7 motion models with random parameters) + platform-motion offset + jitter + measurement noise (sigma 0.3–6 px) + detection dropouts (0–30 % random, plus bursts of 5–30 frames). Input window N = 10, output horizon 1–5 steps.

### 3.6 D4 – Video bank (52 videos)
- Full screen 2000x2000, mono, 30 fps, 30 s (900 frames), H.264 via ffmpeg/OpenCV, with sidecar `*_gt.csv` (`frame, x, y, visible`).
- **Train/dev (40 videos):** 4 motions x 5 atmospheres x noise levels; used to test the `run_video` path and for augmentation-consistency checks.
- **Held-out benchmark (12 videos):** generated with *different seeds and slightly different generator settings* (other background type, unseen shape/size combination, different bitrate). Never used in any training. These mimic the organisers' Benchmark-2 and give our honest score.

## 4. Splits (leak-free)
Splits are by **scene seed**, never by frame or patch (neighbouring frames are near-duplicates).
| Split | Rule | Use |
|---|---|---|
| train | scene_seed % 10 in 0–7 (80 %) | training |
| val | % 10 == 8 (10 %) | model selection, thresholds |
| test | % 10 == 9 (10 %) | final numbers in report |
| test_ood | D4 held-out videos + patches from unseen generator settings | robustness / generalisation |

## 5. File Formats & Layout
```
data/
├── manifests/            # dataset_manifest.json (counts, sha256 per shard, generator version, git commit, config hash)
├── patches/              # shard_0000.npy ... (uint8 [N,32,32], 256 MB each, memory-mappable)
│   └── meta/             # shard_0000.parquet (label, dx, dy, snr, flags, seed, split)
├── frames/
│   ├── viewport/         # shard_0000.npy [5000,480,640] uint8 (~1.5 GB each) + labels parquet
│   └── fullscreen_ds/    # shard_0000.npy [4000,500,500] uint8 (~1 GB each) + labels parquet
├── sequences/            # seq_shard_0000.npy float32 [N,300,2] + meta parquet
├── videos/
│   ├── dev/              # vid_0001.mp4 + vid_0001_gt.csv
│   └── heldout/          # same, never trained on
└── mini/                 # 1 GB subset of everything for quick iteration
```
Raw `.npy` (not compressed) is chosen deliberately: noisy images compress badly anyway, and memmap gives the fastest training I/O.

## 6. Generator Implementation
Entry point: `python -m fsoc.cli.generate_data --config configs/datagen.yaml --budget-gb 40 --workers 8`

**Design**
- Multiprocessing pool; each worker owns a seeded `numpy.random.Generator(PCG64(base_seed + worker_id))`; shards written atomically; **resumable** (skips shards whose sha256 is in the manifest).
- Uses the exact `simulation/` and `disturbances/` modules (single source of truth).
- Streaming: frames are generated, patches extracted, frames dropped (memory stays flat).
- Progress + ETA + running class balance.
- Deterministic: same config + seed -> identical dataset (hash-verified).

**`configs/datagen.yaml` (excerpt)**
```yaml
seed: 20260101
budget_gb: 40
workers: 8
patches:  {count: 16_000_000, size: 32, shard_size: 250_000, pos: 0.375, hard_neg: 0.50, easy_neg: 0.125}
frames_viewport: {count: 25_000, shard_size: 5_000, size: [480, 640], target_absent: 0.10, border: 0.10}
frames_fullscreen: {count: 16_000, screen: 2000, downscale: 4, shard_size: 4_000}
sequences: {count: 400_000, steps: 300, dropout_max: 0.30}
videos: {dev_count: 40, heldout_count: 12, fps: 30, duration_s: 30, screen: 2000, crf: [18, 35]}
severity_mix: {mild: 0.25, moderate: 0.40, severe: 0.25, beyond_spec: 0.10}
ranges:
  target_size_px: [3, 24]
  psf_sigma: [0.3, 2.5]
  sp_density: [0.0, 0.12]
  gaussian_sigma: [0, 25]
  poisson_gain: [0.3, 3.0]
  jitter_px: [0, 24]
  platform_px: [0, 24]
  atmosphere: [clear, haze, fog, rain, low_light]
  jpeg_quality: [40, 95]
splits: {train: [0,1,2,3,4,5,6,7], val: [8], test: [9]}
```

**Expected generation time (8 cores):** ~250 k frames at ~200–300 fps/core -> well under 1 hour for patches; frames < 30 min; videos (encoding dominated) ~1–2 h. Runs unattended.

## 7. Training Plan on This Data
| Model | Data | Setup | Est. cost |
|---|---|---|---|
| Verifier CNN (~7k params, ~0.45 M MAC/patch) | D1 16 M patches | AdamW, batch 2048, OneCycle, 8–10 epochs, mixed precision, hard-negative mining pass after epoch 3 | minutes on a GPU, ~1 h CPU per epoch |
| Heatmap net (small U-Net/ENet-like, < 300 k params) | D2a + D2b | focal + BCE loss, augment: flip/rot90, brightness, extra noise | 2–4 h on a single GPU |
| Motion predictor (GRU 32 units) | D3 | MSE on 1–5 step horizon, trained with dropout bursts | < 30 min |

Training-time augmentation on top of stored data (free, no extra storage): flips, 90° rotations, random gain/bias, extra noise, JPEG.
Export to **ONNX (FP16/INT8)**; inference uses ONNX Runtime only (PyTorch is not shipped in the exe).
Loading: memmap shards + shard-level shuffle + buffered sample shuffle (no need to hold 40 GB in RAM).

**Curriculum:** stage 1 mild/moderate only -> stage 2 all severities -> stage 3 hard-negative fine-tune.

## 8. Quality Checks (automated, run after generation)
1. **Label accuracy:** recompute centroid of the clean target render; must match stored GT within 0.1 px.
2. **Balance:** class ratios, shape/motion/atmosphere frequencies within ±2 % of config.
3. **Distribution plots:** SNR, noise sigma, jitter, size histograms saved to `docs/figures/`.
4. **Visual grid:** 100 random samples per dataset (pos/hard neg) reviewed by a human.
5. **Leakage test:** no `scene_seed` appears in two splits.
6. **Duplicate test:** hash-based near-duplicate check on a 100 k sample.
7. **Reproducibility test:** regenerate one shard and compare sha256.
8. **Video check:** decoded frame count = 900, GT rows = 900, beacon visible per GT.

## 9. Evaluation Protocol (what we report)
Each learned model vs the classical baseline on `test` and `test_ood`:
- Verifier: precision/recall/F1, false-positive rate at fixed recall, ROC-AUC per noise condition, latency (ms), plus effect on the end-to-end system: target loss %, RMSE, acquisition time.
- Heatmap net: centroid error (px), detection rate, acquisition time, FPS.
- Motion predictor: RMSE vs Kalman for 1–5 step prediction, especially during dropouts.
- Full system on the 12 held-out mp4s: RMSE, mean/max error, acquisition/re-acquisition time, lock retention rate, FPS.

## 10. Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Sim-to-real gap (organiser mp4 looks different) | domain randomisation, compression augmentation, out-of-spec severities, ask mentors for a sample video early and add a matching generator preset |
| Storage/IO too slow | raw npy + memmap, SSD, mini-set for iteration |
| Model overfits to generator artefacts | held-out generator settings (test_ood), several background types |
| 16 M patches bring no gain | report honestly; ablation with 1 M / 4 M / 16 M shows the curve; keep the smallest sufficient set for shipping |
| Class imbalance / trivial negatives | 50 % hard negatives, hard-negative mining |
| Data too large to share | ship only generator + config + manifest; dataset is reproducible from seed |

## 11. Execution Order
1. Implement generator on the mini set (1 GB) and run the checks in §8.
2. Train verifier on mini -> verify it beats classical on val.
3. Run full generation (overnight): D1 -> D2 -> D3 -> D4.
4. Full training, ablation on data size, export ONNX.
5. Evaluate on test/test_ood, freeze models, write results into the technical report.
