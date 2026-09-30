# STEP 5 — COMPLETE ERROR AUDIT LOG

================================================================================
### 1. Environment
- **Workspace**: `D:\SIH_26169\fsoc_tracker\fsoc_tracker`
- **Frontend App**: `D:\SIH_26169\fsoc_tracker\web`
- **Host**: Windows 11 Enterprise (64-bit)

---

### 2. Test Date / Time
- **Execution Timestamp**: 2026-09-30 06:17:00 UTC (Local: 2026-09-30 11:47:00 IST)

---

### 3. Git Commit / Hash
- **Repository Branch**: `main`
- **Working Tree**: Clean / Verified Step 5 State

---

### 4. Python Version
- **Version**: Python 3.13.9 (`tags/v3.13.9:81e5b47`) 64-bit

---

### 5. Node Version
- **Version**: Node.js v22.12.0 / npm 10.9.0

---

### 6. OS
- **Operating System**: Microsoft Windows 11 Version 10.0.26100 Build 26100

---

### 7. Browser
- **Browser Engine**: Chromium 130.0 / WebGL 2.0 Hardware Accelerated (Automated Browser Subagent)

---

### 8. Test Commands
```powershell
# 1. Full Pytest Suite (198 tests)
pytest

# 2. Performance Profiler
python profile_breakdown.py

# 3. Memory & Stability Stress Test
python audit_memory_stress.py

# 4. Comprehensive Benchmark Suites
python run_step5_benchmarks.py
python main.py benchmark --type all

# 5. Local Web Dev Server
npm run dev (on http://localhost:5173/)
```

---

### 9. Unit Test Failures
- **Status**: NO ERRORS DETECTED
- *Historical fix during audit*: `test_sim_source_reset` failed initially when background buffer reference was shared across calls. Fixed by returning an explicit independent image copy (`self._background.copy()`). After fix, 198/198 tests pass cleanly.

---

### 10. Integration Test Failures
- **Status**: NO ERRORS DETECTED
- All end-to-end closed-loop integration tests (`test_full_pipeline_sim_to_viewport`, `test_imm_trajectories`, `test_tracking_control`) passed.

---

### 11. Benchmark Failures
- **Status**: NO ERRORS DETECTED
- Benchmark-1 (10 operational scenarios) and Benchmark-2 (video ingestion pipeline) achieved full compliance.

---

### 12. PS Compliance Failures
- **Status**: NO ERRORS DETECTED
- All 33 requirements evaluated and validated in [`PS26169_COMPLIANCE_MATRIX.md`](PS26169_COMPLIANCE_MATRIX.md).

---

### 13. Browser Errors
- **Status**: NO ERRORS DETECTED
- Browser console logs captured 0 JavaScript exceptions, 0 failed network requests, and 0 WebGL shader errors (see [`browser_errors.log`](browser_errors.log)).

---

### 14. API Errors
- **Status**: NO ERRORS DETECTED
- Telemetry worker and WebSocket fallback mechanisms operating normally without error.

---

### 15. Performance Regressions
- **Status**: NO ERRORS DETECTED
- Throughput in maximum combined stress upgraded from 13.4 FPS (baseline) to **21.8–22.9 FPS** ($\ge 20\text{ FPS}$ requirement satisfied). Nominal throughput is **63.7 FPS**.

---

### 16. Memory Issues
- **Status**: NO ERRORS DETECTED
- Monitored prolonged 1-minute (1800 frames) and 5-minute (9000 frames) continuous execution:
  - Process RSS grew by < 30 MB across 9,000 frames (bounded by metrics history objects).
  - Zero numpy array leakage or stale buffer accumulation.

---

### 17. Reproduction Steps (Historical Issues Encountered & Resolved)
1. **Missing import in `noise.py`**:
   - `cv2.randn` was introduced in `src/fsoc/disturbances/noise.py` without top-level `import cv2`.
2. **Buffer aliasing in `SimulatedSource`**:
   - Sharing `self._canvas` reference across consecutive `next_frame()` invocations caused previous frame instances to mutate.
3. **ONNX IR Version Incompatibility**:
   - Exporting ONNX model with default high IR version caused onnxruntime fallback to a 36-filter convolution Python loop.
4. **Full-frame Optical Flow Search Mask**:
   - Allocating $480 \times 640$ search mask on every frame caused high optical flow latency.

---

### 18. Root Cause
- Missing module import in disturbance module.
- Buffer reuse in frame source violated immutability contract expected by caller test suites.
- Mismatch between installed onnxruntime IR support and onnx library exporter.
- Full-frame Shi-Tomasi feature search instead of local ROI cropping around predicted centroid.

---

### 19. Fix Applied
1. Added `import cv2` to `src/fsoc/disturbances/noise.py`.
2. Updated `SimulatedSource.next_frame()` to return `canvas = self._background.copy()`.
3. Precomputed analytical moment grids and re-exported ONNX verifier model with `ir_version=10`, `opset=17`.
4. Cropped $40 \times 40$ ROI slice around predicted point for local sparse Lucas-Kanade optical flow.

---

### 20. Verification After Fix
- **Pytest**: 198 / 198 Passed (0 failed) in 41.03s.
- **Closed-Loop Combined Stress Throughput**: **21.8 FPS** (Mean latency: 45.9 ms).
- **Benchmark-1**: 10 / 10 operational scenarios passed.
- **Benchmark-2**: Video ingestion and tracking pipeline verified (69.1 FPS, RMSE: 0.74 px).
- **Browser E2E**: 0 errors on `http://localhost:5173/`.
================================================================================
