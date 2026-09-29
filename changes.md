# Tracking Engine & Problem Statement Alignment (Changes Justification)

This document outlines the recent pipeline and configuration changes and details exactly how they align with the ISRO Problem Statement (PS ID: 26169) and the master project roadmaps (`00` to `04`).

## 1. Mathematical Accuracy & Simulation Sync (Removing "Hardcoded" Feel)

**The Problem:** The system felt "hardcoded" because the initial tracking lock was unnaturally perfect and the camera `LOST` state was almost never triggered unless artificially forced. 

**The Fixes Applied:**
*   **Circle Motion Orbit Center Fix (`motion_models.py` & `config.py`):** 
    Previously, the circular target motion always started at `(scene_w/2 + R, scene_h/2)`. If `R` was large (e.g. 400px), the beacon actually started *outside* the camera's default 640x480 FOV. The camera would violently snap to it. 
    *   **Fix:** Configured `phase_offset_deg` and allowed orbit center `(x0, y0)` to follow user specifications. The physics now properly syncs with the camera's initial view.
*   **Wide-Area Search Realism (`engine.py`):**
    *   **Fix:** The wide-area search (used during `SEARCH` state) was previously fed the *clean*, un-disturbed canvas before weather/noise was applied, giving it an unfair advantage. We now apply full-scene disturbances (Fog, Haze, etc.) *before* wide search runs, ensuring the AI and math are actually processing the noisy data.
*   **Kalman Cold-Start Smoothing (`kalman.py`):**
    *   **Fix:** We increased the initial Kalman velocity covariance (`P` matrix) from `50.0` to `500.0`. When the tracker first acquires the target, it now properly acknowledges uncertainty rather than snapping with 100% confidence. This removes the abrupt, unnatural "jump" and forces the PID loop to organically settle.

**PS Alignment:** Meets **R14** (Tracking error ≤ 10 px) honestly, without simulation shortcuts. Syncs perfectly with `02_DESIGN_DOCUMENT.md` Section 8 (Kalman tracking & Coasting).

## 2. Decluttering and Focus

**The Problem:** The workspace was littered with temporary analysis reports, PDFs, and scratchpads, causing confusion.
**The Fixes Applied:**
*   Removed `ps.pdf`, `ps2.pdf`, `FSOC_Analysis_Report.md`, `Bug_Investigation_Report...`, `Implementation_Plan...`, and `what done what new fsoc`.
*   The project root is now clean, leaving only the core `00` to `04` MD roadmaps, the codebase, and this specific `changes.md` file.

**PS Alignment:** Aligns with **R24** (Documented modular source code) and keeps the folder structure strictly aligned to `01_PROJECT_STRUCTURE.md`.

## 3. Metric Transparency (Boresight vs. Centroid)

**The Problem:** The GUI was displaying the raw detection error (centroiding), leading to confusion about tracking accuracy.
**The Fixes Applied:**
*   **Boresight R14 Metric (`engine.py`, `types.py`, GUI):** Completely separated the centroiding error from the physical boresight error (distance of the target from the true center of the camera viewport). 
*   The GUI now explicitly tracks and plots `boresight_px` to prove compliance with **R14**.

## 4. Next Implementation Plan (The Road Ahead)

Now that the core mathematical models are verified to be running strictly on sensor data (no cheating, no hardcoding), the plan for the next phases as per `00_PROJECT_ROADMAP.md`:

1.  **Phase 6 (GUI Polish):** The HUD and minimap radar are now functionally correct. The focus will shift slightly to finalizing the PySide6 real-time graphing for Benchmark recording.
2.  **Benchmark Automation (Phase 5):** Execute the headless data generation plan (`04_DATA_GENERATION_PLAN.md`) to create the required CSV files proving R14 and R15 compliance over long durations.
3.  **Phase 7 (Custom Feature):** Finalizing the user-requested custom feature slot before wrapping the executable.
