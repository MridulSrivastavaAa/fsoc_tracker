# 04. DATA GENERATION PLAN

## Benchmark frames generated
- `fsoc_tracker/test_videos/01_clear_sky_decoy_10s_gt.csv` — clear sky, decoy, 10 s, ground-truth CSV
- `fsoc_tracker/test_videos/02_haze_moving_glint_10s_gt.csv` — haze + moving glint
- `fsoc_tracker/test_videos/03_dense_fog_flickering_glint_10s_gt.csv` — dense fog, flickering glint
- `fsoc_tracker/test_videos/04_rain_streaks_decoys_10s_gt.csv` — rain streaks + decoys
- `fsoc_tracker/test_videos/05_hard_turbulence_deep_fade_10s_gt.csv` — hard turbulence + deep fade
- `fsoc_tracker/web/public/fsoc_test_video_30s_60fps_truth.csv` — 30 s / 60 fps reference
- `fsoc_tracker/web/public/test_videos/01_...`, `02_...`, ... — render-ready frame sets

## Ground-truth CSV schema (per frame)
`frame,x_px,y_px` — beacon true pixel position (x right, y down).

## Benchmark pipeline
- `fsoc_tracker/fsoc_engine/run_benchmarks.bat` — batch-run the engine on all videos.
- `fsoc_tracker/fsoc_engine/generate_test_video.py`, `generate_decoy_benchmark_videos.py`, `generate_multi_tier_videos.py` — video generators.
- Results → `benchmark1_results.json`, `benchmark2_results.json`, `performance_results.json`, `ablation_results.json`.

## Validation target (R13/R14/R15/R22 from PS26169 COMPLIANCE_MATRIX)
- R13 acquisition ≤ 2 s
- R14 centroid RMSE ≤ 10 px
- R15 target-loss rate < 5 %
- R22 processing rate ≥ 30 FPS
