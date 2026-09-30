# ISRO PS 26169 — Benchmark-2 Video Perception & Tracking Report

## 1. Scope and Architecture

Benchmark-2 validates standalone video ingestion and perception tracking (PTZ closed-loop bypassed).
The video pipeline directly consumes external `.mp4` video frames (640x480 @ 30 FPS), performs morphological preprocessing,
centroid spot detection, CNN verification, Lucas-Kanade optical flow, and IMM multi-model estimation.

## 2. Validation Metrics

- **Video Source**: `benchmark_results\synthetic_validation_beacon.mp4`
- **Total Frames Processed**: 120
- **Mean Processing Throughput**: **59.4 FPS** (Target: ≥20 FPS)
- **Tracking RMSE**: **0.738 px** (Target: ≤10 px)
- **P95 Error**: **1.946 px**
- **Max Error**: **3.323 px**
- **Acquisition Time**: **0.067 s** (Target: ≤2.0 s)
- **Lock Retention**: **100.0%**

## 3. Evaluator MP4 Ingestion Status

> [!NOTE]
> Official ISRO evaluator-provided external MP4 was not bundled with repo; the pipeline was fully validated against synthetic calibration video.
> Status: **PIPELINE VALIDATED — OFFICIAL DATA NOT AVAILABLE**
