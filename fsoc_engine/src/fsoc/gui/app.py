"""
src/fsoc/gui/app.py
===================
Interactive Desktop GUI Application for FSOC Optical Tracking.
Features:
- Dark glassmorphic Mission Control telemetry aesthetic
- Real-time 640x480 HUD viewport with reticle, crosshair, and 2000x2000 radar minimap
- Live rolling tracking error plot
- Interactive disturbance injection panel (S&P noise, Gaussian, Fog, Rain, Haze)
- Manual / Autonomous gimbal steering controls
- Benchmark-2 Video file ingestion & playback
"""
from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk
import cv2

from ..core.config import AppConfig, default_config
from ..core.engine import ClosedLoopEngine
from ..core.types import FrameMetrics, Point, CameraCommand
from ..video.video_source import VideoFileSource
from .live_overlay import HUDOverlayRenderer


# Styling Tokens
THEME_BG = "#0d1117"
THEME_SURFACE = "#161b22"
THEME_SURFACE2 = "#21262d"
THEME_BORDER = "#30363d"
THEME_TEXT = "#e6edf3"
THEME_MUTED = "#8b949e"
THEME_CYAN = "#38bdf8"
THEME_GREEN = "#3fb950"
THEME_RED = "#f85149"
THEME_AMBER = "#d29922"


# Full scene dimensions (must match config)
_SCENE_W = 2000
_SCENE_H = 2000
_MINIMAP_PX = 220   # minimap canvas size in screen pixels
_MINIMAP_SCALE = _MINIMAP_PX / _SCENE_W


class FSOCTrackerApp:
    """
    Main desktop GUI application for the FSOC tracking system.
    """
    def __init__(self, root: tk.Tk, cfg: Optional[AppConfig] = None) -> None:
        self.root = root
        self.root.title("ISRO FSOC Virtual Camera Tracking Telemetry & Control Workstation")
        self.root.geometry("1180x820")
        self.root.configure(bg=THEME_BG)
        self.root.minsize(1050, 750)

        self.cfg = cfg or default_config()
        self.engine = ClosedLoopEngine(self.cfg)
        self.hud_renderer = HUDOverlayRenderer(
            res_x=self.cfg.camera.res_x, res_y=self.cfg.camera.res_y
        )

        # Execution flags
        self.is_running = False
        self.is_manual_mode = False
        self.manual_pan_rate = 0.0
        self.manual_tilt_rate = 0.0
        self.worker_thread: Optional[threading.Thread] = None

        # Data buffer for plot
        self.error_history: list[float] = []
        self.max_history_len = 80

        # Minimap trail data (screen-coordinate positions)
        self.minimap_gt_trail: list[tuple[float, float]] = []    # ground truth positions
        self.minimap_est_trail: list[tuple[float, float]] = []   # estimated track positions
        self.minimap_max_trail = 60                              # frames of trail to show

        # Build UI layout
        self._setup_styles()
        self._build_header()
        self._build_main_layout()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=THEME_BG, foreground=THEME_TEXT, bordercolor=THEME_BORDER)
        style.configure("TFrame", background=THEME_BG)
        style.configure("Surface.TFrame", background=THEME_SURFACE)
        style.configure("TLabel", background=THEME_SURFACE, foreground=THEME_TEXT, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=THEME_SURFACE, foreground=THEME_CYAN, font=("Segoe UI", 11, "bold"))
        style.configure("StatVal.TLabel", background=THEME_SURFACE2, foreground=THEME_GREEN, font=("Segoe UI", 14, "bold"))
        style.configure("StatLbl.TLabel", background=THEME_SURFACE2, foreground=THEME_MUTED, font=("Segoe UI", 8))
        style.configure("TButton", background=THEME_SURFACE2, foreground=THEME_TEXT, bordercolor=THEME_BORDER, font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#30363d")])

    def _build_header(self) -> None:
        header_frame = tk.Frame(self.root, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=16, pady=10)
        header_frame.pack(fill=tk.X, padx=12, pady=(10, 6))

        title_lbl = tk.Label(
            header_frame,
            text="ISRO / SAC PS 26169 — FSOC VIRTUAL CAMERA TRACKING SYSTEM",
            bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 12, "bold")
        )
        title_lbl.pack(side=tk.LEFT)

        self.status_badge = tk.Label(
            header_frame,
            text="STATE: IDLE",
            bg="#1a3a21", fg=THEME_GREEN, font=("Segoe UI", 9, "bold"),
            padx=10, pady=3, bd=1, relief=tk.SOLID
        )
        self.status_badge.pack(side=tk.RIGHT)

    def _build_main_layout(self) -> None:
        body = tk.Frame(self.root, bg=THEME_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        # Left Column: Viewport & Live Chart
        left_col = tk.Frame(body, bg=THEME_BG)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        # Viewport Frame
        vp_card = tk.Frame(left_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=6, pady=6)
        vp_card.pack(fill=tk.BOTH, expand=True)

        self.canvas_vp = tk.Canvas(
            vp_card, width=640, height=480, bg="#000000",
            highlightthickness=1, highlightbackground=THEME_BORDER
        )
        self.canvas_vp.pack(anchor=tk.CENTER, pady=4)

        # Plot Canvas (Rolling Error)
        plot_card = tk.Frame(left_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=8, pady=6)
        plot_card.pack(fill=tk.X, pady=(6, 0))

        tk.Label(plot_card, text="REAL-TIME TRACKING ERROR (px) — LIMIT: 10 px", bg=THEME_SURFACE, fg=THEME_MUTED, font=("Segoe UI", 8, "bold")).pack(anchor=tk.W)
        self.plot_canvas = tk.Canvas(plot_card, height=90, bg="#010409", highlightthickness=1, highlightbackground=THEME_BORDER)
        self.plot_canvas.pack(fill=tk.X, pady=4)

        # Right Column (Outer Container)
        right_outer = tk.Frame(body, bg=THEME_BG, width=380)
        right_outer.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        right_outer.pack_propagate(False)

        # Scrollable Canvas
        right_canvas = tk.Canvas(right_outer, bg=THEME_BG, highlightthickness=0, width=360)
        right_scrollbar = ttk.Scrollbar(right_outer, orient="vertical", command=right_canvas.yview)
        right_col = tk.Frame(right_canvas, bg=THEME_BG)

        right_col.bind("<Configure>", lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
        right_canvas.create_window((0, 0), window=right_col, anchor="nw", width=360)
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


        # 1. Telemetry Cards Grid
        telemetry_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        telemetry_frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(telemetry_frame, text="FLIGHT TELEMETRY", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        stats_grid = tk.Frame(telemetry_frame, bg=THEME_SURFACE)
        stats_grid.pack(fill=tk.X)

        self.val_error = self._create_stat_box(stats_grid, "DETECT ERR", "-- px", 0, 0)
        self.val_boresight = self._create_stat_box(stats_grid, "BORESIGHT (R14)", "-- px", 0, 1)
        self.val_pan = self._create_stat_box(stats_grid, "PAN ANGLE", "0.00°", 1, 0)
        self.val_tilt = self._create_stat_box(stats_grid, "TILT ANGLE", "0.00°", 1, 1)
        self.val_fps = self._create_stat_box(stats_grid, "LOOP FPS", "-- FPS", 2, 0)
        self.val_conf = self._create_stat_box(stats_grid, "TRACK CONF", "0.00", 2, 1)

        # 2. Main Playback Controls
        ctrl_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        ctrl_frame.pack(fill=tk.X, pady=6)

        tk.Label(ctrl_frame, text="OPERATOR CONTROLS", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        btn_box = tk.Frame(ctrl_frame, bg=THEME_SURFACE)
        btn_box.pack(fill=tk.X)

        self.btn_start = tk.Button(btn_box, text="► START", bg="#1a3a21", fg=THEME_GREEN, font=("Segoe UI", 9, "bold"), command=self.toggle_start)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.btn_step = tk.Button(btn_box, text="STEP", bg=THEME_SURFACE2, fg=THEME_TEXT, font=("Segoe UI", 9), command=self.step_frame)
        self.btn_step.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.btn_reset = tk.Button(btn_box, text="RESET", bg=THEME_SURFACE2, fg=THEME_TEXT, font=("Segoe UI", 9), command=self.reset_system)
        self.btn_reset.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # 3D Mission Control Launcher Button
        self.btn_3d = tk.Button(
            ctrl_frame,
            text="🌐 LAUNCH 3D ORBIT MISSION CONTROL",
            bg="#0f2b38",
            fg=THEME_CYAN,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief=tk.SOLID,
            command=self._launch_3d,
        )
        self.btn_3d.pack(fill=tk.X, pady=(8, 2))

        # Plugin Playground Launcher Button
        self.btn_plugin = tk.Button(
            ctrl_frame,
            text="⚡ ALGORITHM PLUGIN PLAYGROUND",
            bg="#1e1b4b",
            fg=THEME_CYAN,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief=tk.SOLID,
            command=self._launch_plugin_playground,
        )
        self.btn_plugin.pack(fill=tk.X, pady=(4, 2))

        # Mode Selection
        mode_box = tk.Frame(ctrl_frame, bg=THEME_SURFACE)
        mode_box.pack(fill=tk.X, pady=(8, 0))
        tk.Label(mode_box, text="Motion Model:", bg=THEME_SURFACE, fg=THEME_MUTED).pack(side=tk.LEFT)
        self.combo_motion = ttk.Combobox(mode_box, values=["circle", "line", "figure8", "random", "spiral", "sinusoidal"], state="readonly", width=12)
        self.combo_motion.set(self.cfg.motion.model)
        self.combo_motion.pack(side=tk.RIGHT)
        self.combo_motion.bind("<<ComboboxSelected>>", self._on_motion_change)

        # 3. Environmental Disturbances Injection
        dist_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        dist_frame.pack(fill=tk.X, pady=6)

        tk.Label(dist_frame, text="DISTURBANCE INJECTION", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))

        # Salt & Pepper
        self.var_sp = tk.BooleanVar(value=False)
        chk_sp = tk.Checkbutton(dist_frame, text="Salt & Pepper Noise (10%)", variable=self.var_sp, bg=THEME_SURFACE, fg=THEME_TEXT, selectcolor=THEME_SURFACE2, command=self._apply_disturbances)
        chk_sp.pack(anchor=tk.W)

        # Gaussian Noise
        self.var_gauss = tk.BooleanVar(value=False)
        chk_gauss = tk.Checkbutton(dist_frame, text="Gaussian Noise (σ=15)", variable=self.var_gauss, bg=THEME_SURFACE, fg=THEME_TEXT, selectcolor=THEME_SURFACE2, command=self._apply_disturbances)
        chk_gauss.pack(anchor=tk.W)

        # Camera Jitter
        self.var_jitter = tk.BooleanVar(value=False)
        chk_jitter = tk.Checkbutton(dist_frame, text="Camera Jitter (±10 px)", variable=self.var_jitter, bg=THEME_SURFACE, fg=THEME_TEXT, selectcolor=THEME_SURFACE2, command=self._apply_disturbances)
        chk_jitter.pack(anchor=tk.W)

        # Turbulence
        self.var_turb = tk.BooleanVar(value=False)
        chk_turb = tk.Checkbutton(dist_frame, text="Optical Turbulence", variable=self.var_turb, bg=THEME_SURFACE, fg=THEME_TEXT, selectcolor=THEME_SURFACE2, command=self._apply_disturbances)
        chk_turb.pack(anchor=tk.W)

        # Atmosphere Condition
        atmo_box = tk.Frame(dist_frame, bg=THEME_SURFACE)
        atmo_box.pack(fill=tk.X, pady=(6, 0))
        tk.Label(atmo_box, text="Atmosphere:", bg=THEME_SURFACE, fg=THEME_MUTED).pack(side=tk.LEFT)
        self.combo_atmo = ttk.Combobox(atmo_box, values=["clear", "haze", "fog", "rain", "low_light"], state="readonly", width=12)
        self.combo_atmo.set("clear")
        self.combo_atmo.pack(side=tk.RIGHT)
        self.combo_atmo.bind("<<ComboboxSelected>>", self._apply_disturbances)

        # Stress Test button — all disturbances at failure-inducing levels
        btn_stress = tk.Button(
            dist_frame, text="⚡ STRESS TEST (All Disturbances Max)",
            bg="#3a1a1a", fg=THEME_RED, font=("Segoe UI", 9, "bold"),
            command=self._apply_stress_test
        )
        btn_stress.pack(fill=tk.X, pady=(8, 0))

        # Reset disturbances
        btn_clear_dist = tk.Button(
            dist_frame, text="✕ Clear All Disturbances",
            bg=THEME_SURFACE2, fg=THEME_MUTED, font=("Segoe UI", 8),
            command=self._clear_disturbances
        )
        btn_clear_dist.pack(fill=tk.X, pady=(2, 0))

        # 4. Benchmark 2 Video File Selector
        video_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        video_frame.pack(fill=tk.X, pady=6)

        tk.Label(video_frame, text="BENCHMARK-2 VIDEO BYPASS", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        btn_video = tk.Button(video_frame, text="\U0001f4c2 Load .mp4 Video Feed", bg=THEME_SURFACE2, fg=THEME_TEXT, command=self._open_video_file)
        btn_video.pack(fill=tk.X, pady=2)

        # 5. Radar Minimap
        self._build_minimap_card(right_col)

    def _build_minimap_card(self, parent: tk.Frame) -> None:
        """
        Build the 2000x2000 radar minimap card in the right column.
        Shows: camera FOV rectangle (cyan), ground truth beacon (green dot),
        estimated track position (amber cross), and motion trails.
        """
        radar_card = tk.Frame(parent, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=8, pady=8)
        radar_card.pack(fill=tk.X, pady=(6, 0))

        # Header row
        header_row = tk.Frame(radar_card, bg=THEME_SURFACE)
        header_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(header_row, text="SCENE RADAR — 2000×2000 px", bg=THEME_SURFACE, fg=THEME_CYAN,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        # Legend row
        legend_row = tk.Frame(radar_card, bg=THEME_SURFACE)
        legend_row.pack(fill=tk.X, pady=(0, 4))
        for symbol, label, color in [
            ("■", "Camera FOV", THEME_CYAN),
            ("●", "Beacon GT", THEME_GREEN),
            ("✕", "Estimated", "#d29922"),
        ]:
            tk.Label(legend_row, text=f"{symbol} {label}", bg=THEME_SURFACE, fg=color,
                     font=("Segoe UI", 7)).pack(side=tk.LEFT, padx=4)

        # Minimap canvas — square, scene-proportional
        self.canvas_radar = tk.Canvas(
            radar_card, width=_MINIMAP_PX, height=_MINIMAP_PX,
            bg="#010409", highlightthickness=1, highlightbackground=THEME_BORDER
        )
        self.canvas_radar.pack(anchor=tk.CENTER, pady=2)

        # Draw static grid lines on minimap background
        grid_step = int(_MINIMAP_PX / 4)
        for i in range(1, 4):
            x = i * grid_step
            self.canvas_radar.create_line(x, 0, x, _MINIMAP_PX, fill="#1a2233", width=1)
            self.canvas_radar.create_line(0, x, _MINIMAP_PX, x, fill="#1a2233", width=1)

        # Draw static border
        self.canvas_radar.create_rectangle(
            1, 1, _MINIMAP_PX - 1, _MINIMAP_PX - 1, outline=THEME_BORDER, width=1
        )

        # Label: RADAR
        self.canvas_radar.create_text(
            6, 6, anchor=tk.NW, text="RADAR", fill="#30363d",
            font=("Segoe UI", 7, "bold")
        )

    def _update_minimap(
        self,
        cam_cx: float,
        cam_cy: float,
        gt_x: Optional[float],
        gt_y: Optional[float],
        est_x: Optional[float],
        est_y: Optional[float],
        state: str,
    ) -> None:
        """
        Redraw the radar minimap each frame.
        All scene coordinates are in 2000x2000 screen pixels.
        """
        c = self.canvas_radar
        c.delete("dynamic")  # clear only dynamic items, preserve static background

        s = _MINIMAP_SCALE  # pixels per scene pixel on minimap

        # --- Ground truth trail ---
        if gt_x is not None and gt_y is not None:
            self.minimap_gt_trail.append((gt_x, gt_y))
            if len(self.minimap_gt_trail) > self.minimap_max_trail:
                self.minimap_gt_trail.pop(0)

        for i in range(1, len(self.minimap_gt_trail)):
            x0, y0 = self.minimap_gt_trail[i - 1]
            x1, y1 = self.minimap_gt_trail[i]
            alpha = int(80 + 175 * i / max(1, len(self.minimap_gt_trail)))
            col = f"#{0:02x}{alpha:02x}{0:02x}"  # dim green fading to bright
            c.create_line(
                x0 * s, y0 * s, x1 * s, y1 * s,
                fill=col, width=1, tags="dynamic"
            )

        # --- Ground truth beacon dot (bright green circle) ---
        if gt_x is not None and gt_y is not None:
            mx, my = gt_x * s, gt_y * s
            c.create_oval(
                mx - 3, my - 3, mx + 3, my + 3,
                fill=THEME_GREEN, outline="", tags="dynamic"
            )

        # --- Estimated position trail ---
        if est_x is not None and est_y is not None:
            self.minimap_est_trail.append((est_x, est_y))
            if len(self.minimap_est_trail) > self.minimap_max_trail:
                self.minimap_est_trail.pop(0)

        for i in range(1, len(self.minimap_est_trail)):
            x0, y0 = self.minimap_est_trail[i - 1]
            x1, y1 = self.minimap_est_trail[i]
            c.create_line(
                x0 * s, y0 * s, x1 * s, y1 * s,
                fill="#4a3800", width=1, tags="dynamic"
            )

        # --- Estimated position cross (amber) ---
        if est_x is not None and est_y is not None:
            mx, my = est_x * s, est_y * s
            r = 3
            c.create_line(mx - r, my, mx + r, my, fill="#d29922", width=2, tags="dynamic")
            c.create_line(mx, my - r, mx, my + r, fill="#d29922", width=2, tags="dynamic")

        # --- Camera FOV rectangle (cyan) ---
        cam_vp_half_w = (640 / 2) * s
        cam_vp_half_h = (480 / 2) * s
        rx0 = cam_cx * s - cam_vp_half_w
        ry0 = cam_cy * s - cam_vp_half_h
        rx1 = cam_cx * s + cam_vp_half_w
        ry1 = cam_cy * s + cam_vp_half_h

        # State-based FOV box colour
        fov_color_map = {
            "TRACK": THEME_CYAN,
            "ACQUIRE": "#22d3ee",
            "SEARCH": "#0e7490",
            "LOST": THEME_RED,
            "REACQUIRE": "#a855f7",
        }
        fov_col = fov_color_map.get(state, THEME_CYAN)

        c.create_rectangle(rx0, ry0, rx1, ry1, outline=fov_col, width=1, tags="dynamic")

        # Corner tick marks on FOV box
        tick = 4
        for px, py in [(rx0, ry0), (rx1, ry0), (rx0, ry1), (rx1, ry1)]:
            dx = tick if px == rx0 else -tick
            dy = tick if py == ry0 else -tick
            c.create_line(px, py, px + dx, py, fill=fov_col, width=1, tags="dynamic")
            c.create_line(px, py, px, py + dy, fill=fov_col, width=1, tags="dynamic")

        # Camera centre crosshair dot
        cx_m, cy_m = cam_cx * s, cam_cy * s
        c.create_oval(
            cx_m - 1, cy_m - 1, cx_m + 1, cy_m + 1,
            fill=fov_col, outline="", tags="dynamic"
        )

    def _create_stat_box(self, parent: tk.Frame, label: str, init_val: str, row: int, col: int) -> tk.Label:
        box = tk.Frame(parent, bg=THEME_SURFACE2, bd=1, relief=tk.SOLID, padx=8, pady=4)
        box.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
        parent.grid_columnconfigure(col, weight=1)

        val_lbl = tk.Label(box, text=init_val, bg=THEME_SURFACE2, fg=THEME_GREEN, font=("Segoe UI", 11, "bold"))
        val_lbl.pack()
        lbl_lbl = tk.Label(box, text=label, bg=THEME_SURFACE2, fg=THEME_MUTED, font=("Segoe UI", 7))
        lbl_lbl.pack()
        return val_lbl

    def _on_motion_change(self, event=None) -> None:
        model = self.combo_motion.get()
        self.cfg.motion.model = model
        self.engine = ClosedLoopEngine(self.cfg)
        self._apply_disturbances()
        self.reset_system()

    def _launch_3d(self) -> None:
        """Launch the Native 3D Earth & Orbit Mission Control Window."""
        from .app_3d import launch_3d_desktop
        t = threading.Thread(target=launch_3d_desktop, daemon=True)
        t.start()

    def _apply_disturbances(self, event=None) -> None:
        # Salt & Pepper
        if self.var_sp.get():
            self.engine.disturbances.salt_pepper.enabled = True
            self.engine.disturbances.salt_pepper.density = 0.10
        else:
            self.engine.disturbances.salt_pepper.enabled = False

        # Gaussian
        if self.var_gauss.get():
            self.engine.disturbances.gaussian.enabled = True
            self.engine.disturbances.gaussian.sigma = 15.0
        else:
            self.engine.disturbances.gaussian.enabled = False

        # Camera Jitter
        if self.var_jitter.get():
            self.engine.disturbances.jitter.enabled = True
            self.engine.disturbances.jitter.max_px = 10.0
        else:
            self.engine.disturbances.jitter.enabled = False

        # Optical Turbulence
        if self.var_turb.get():
            self.engine.disturbances.turbulence.enabled = True
            self.engine.disturbances.turbulence.wander_max_px = 3.0
            self.engine.disturbances.turbulence.scintillation_sigma = 0.15
            self.engine.disturbances.turbulence.blur_sigma = 0.5
        else:
            self.engine.disturbances.turbulence.enabled = False

        # Atmosphere
        atmo = self.combo_atmo.get()
        self.engine.disturbances.atmosphere.set_condition(atmo, strength=0.8)

    def _apply_stress_test(self) -> None:
        """Activate all disturbances at PS-specified maximum levels to genuinely stress the pipeline."""
        # These magnitudes are chosen to exceed normal preprocessing headroom:
        # S&P 20% density: median filter fails, false positives overwhelm CNN
        # Gaussian sigma=25: exceeds MAD headroom for faint beacons
        # Jitter 20px: challenges tracking gate association
        # Fog strength=0.95: reduces beacon contrast near SNR floor
        self.engine.disturbances.salt_pepper.enabled = True
        self.engine.disturbances.salt_pepper.density = 0.20
        self.engine.disturbances.gaussian.enabled = True
        self.engine.disturbances.gaussian.sigma = 25.0
        self.engine.disturbances.jitter.enabled = True
        self.engine.disturbances.jitter.max_px = 20.0
        self.engine.disturbances.turbulence.enabled = True
        self.engine.disturbances.turbulence.wander_max_px = 8.0
        self.engine.disturbances.turbulence.scintillation_sigma = 0.30
        self.engine.disturbances.turbulence.blur_sigma = 1.5
        self.engine.disturbances.atmosphere.set_condition("fog", strength=0.95)
        # Sync checkboxes
        self.var_sp.set(True)
        self.var_gauss.set(True)
        self.var_jitter.set(True)
        self.var_turb.set(True)
        self.combo_atmo.set("fog")

    def _clear_disturbances(self) -> None:
        """Disable all disturbances and reset checkboxes."""
        self.var_sp.set(False)
        self.var_gauss.set(False)
        self.var_jitter.set(False)
        self.var_turb.set(False)
        self.combo_atmo.set("clear")
        self._apply_disturbances()

    def _open_video_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov"), ("All files", "*.*")]
        )
        if path:
            try:
                video_src = VideoFileSource(path)
                self.engine = ClosedLoopEngine(self.cfg, source=video_src)
                messagebox.showinfo("Video Loaded", f"Successfully loaded video:\n{Path(path).name}")
                self.step_frame()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load video:\n{e}")

    def toggle_start(self) -> None:
        if self.is_running:
            self.is_running = False
            self.btn_start.configure(text="► START", bg="#1a3a21", fg=THEME_GREEN)
        else:
            self.is_running = True
            self.btn_start.configure(text="❚❚ PAUSE", bg="#3a211a", fg=THEME_RED)
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._run_loop, daemon=True)
                self.worker_thread.start()

    def _run_loop(self) -> None:
        while self.is_running:
            t0 = time.perf_counter()
            metric = self.engine.step()
            if metric is None:
                self.is_running = False
                self.root.after(0, lambda: self.btn_start.configure(text="► START", bg="#1a3a21", fg=THEME_GREEN))
                break

            self.root.after(0, self._update_ui, metric)
            # Regulate frame rate to ~30 FPS
            dt = time.perf_counter() - t0
            sleep_time = max(0.001, (1.0 / 30.0) - dt)
            time.sleep(sleep_time)

    def step_frame(self) -> None:
        metric = self.engine.step()
        if metric is not None:
            self._update_ui(metric)

    def reset_system(self) -> None:
        self.is_running = False
        self.btn_start.configure(text="► START", bg="#1a3a21", fg=THEME_GREEN)
        self.engine.reset()
        self._apply_disturbances()
        self.error_history.clear()
        self.minimap_gt_trail.clear()
        self.minimap_est_trail.clear()
        self.plot_canvas.delete("all")
        self.canvas_radar.delete("dynamic")
        self.val_error.configure(text="-- px")
        self.val_boresight.configure(text="-- px", fg=THEME_MUTED)
        self.val_fps.configure(text="-- FPS")
        self.val_pan.configure(text="0.00°")
        self.val_tilt.configure(text="0.00°")
        self.val_conf.configure(text="0.00")
        self.status_badge.configure(text="STATE: IDLE", bg="#1a3a21", fg=THEME_GREEN)

    def _update_ui(self, metric: FrameMetrics) -> None:
        # 1. Update telemetry cards
        err_text = f"{metric.error_px:.2f} px" if metric.error_px is not None else "-- px"
        fps = 1000.0 / max(0.1, metric.proc_ms)
        self.val_error.configure(text=err_text)
        self.val_fps.configure(text=f"{fps:.1f} FPS")
        self.val_pan.configure(text=f"{metric.pan_deg:+.2f}°")
        self.val_tilt.configure(text=f"{metric.tilt_deg:+.2f}°")
        self.val_conf.configure(text=f"{metric.confidence:.2f}")

        # Boresight metric — colour code by ISRO R14 compliance (≤10 px)
        if metric.boresight_px is not None:
            bs_text = f"{metric.boresight_px:.1f} px"
            if metric.boresight_px <= 10.0:
                self.val_boresight.configure(text=bs_text, fg=THEME_GREEN)
            elif metric.boresight_px <= 30.0:
                self.val_boresight.configure(text=bs_text, fg=THEME_AMBER)
            else:
                self.val_boresight.configure(text=bs_text, fg=THEME_RED)
        else:
            self.val_boresight.configure(text="-- px", fg=THEME_MUTED)

        # 2. Update status pill
        badge_colors = {
            "SEARCH": ("#3a301a", THEME_AMBER),
            "ACQUIRE": ("#1a2e3a", THEME_CYAN),
            "TRACK": ("#1a3a21", THEME_GREEN),
            "LOST": ("#3a1a1a", THEME_RED),
            "REACQUIRE": ("#2e1a3a", "#c084fc"),
        }
        bg_col, fg_col = badge_colors.get(metric.state, ("#21262d", THEME_MUTED))
        self.status_badge.configure(text=f"STATE: {metric.state}", bg=bg_col, fg=fg_col)

        # 3. Render HUD and draw on Viewport Canvas
        raw_img = (
            self.engine.last_viewport
            if self.engine.last_viewport is not None
            else np.zeros((self.cfg.camera.res_y, self.cfg.camera.res_x), dtype=np.uint8)
        )
        tgt_pt = Point(metric.gt_x, metric.gt_y) if metric.gt_x is not None else None

        hud_bgr = self.hud_renderer.render_hud(
            raw_img,
            metrics=metric,
            track_state=self.engine.kalman.get_state(),
            cam_cx=self.engine.camera.cx,
            cam_cy=self.engine.camera.cy,
            target_scene_pt=tgt_pt,
        )

        # Convert OpenCV BGR to Tkinter PhotoImage
        rgb_img = cv2.cvtColor(hud_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        self.tk_img = ImageTk.PhotoImage(image=pil_img)
        self.canvas_vp.create_image(0, 0, anchor=tk.NW, image=self.tk_img)

        # 4. Update rolling error plot (boresight_px is the R14 compliance metric)
        plot_val = metric.boresight_px if metric.boresight_px is not None else metric.error_px
        if plot_val is not None:
            self.error_history.append(plot_val)
            if len(self.error_history) > self.max_history_len:
                self.error_history.pop(0)
            self._draw_error_plot()

        # 5. Update radar minimap
        self._update_minimap(
            cam_cx=self.engine.camera.cx,
            cam_cy=self.engine.camera.cy,
            gt_x=metric.gt_x,
            gt_y=metric.gt_y,
            est_x=metric.est_x,
            est_y=metric.est_y,
            state=metric.state,
        )

    def _draw_error_plot(self) -> None:
        self.plot_canvas.delete("all")
        w = self.plot_canvas.winfo_width()
        h = self.plot_canvas.winfo_height()
        if w < 50 or not self.error_history:
            return

        max_y_scale = max(50.0, max(self.error_history) * 1.1)  # auto-scale to data

        # Reference lines
        # 10 px R14 compliance limit (green)
        y_r14 = h - int((10.0 / max_y_scale) * h)
        self.plot_canvas.create_line(0, y_r14, w, y_r14, fill="#3fb950", dash=(4, 4), width=1)
        self.plot_canvas.create_text(w - 32, y_r14 - 7, text="R14: 10px", fill="#3fb950", font=("Segoe UI", 7))

        # 30 px secondary warning (amber)
        y_warn = h - int((30.0 / max_y_scale) * h)
        if y_warn > 0:
            self.plot_canvas.create_line(0, y_warn, w, y_warn, fill="#d29922", dash=(2, 6), width=1)
            self.plot_canvas.create_text(w - 24, y_warn - 7, text="30px", fill="#d29922", font=("Segoe UI", 7))

        # Plot data points (colour by R14 compliance)
        dx = w / float(self.max_history_len)
        pts: list[tuple[float, float]] = []
        for i, val in enumerate(self.error_history):
            px = i * dx
            norm_val = min(val, max_y_scale) / max_y_scale
            py = h - int(norm_val * (h - 8)) - 4
            pts.append((px, py))

        for j in range(len(pts) - 1):
            v = self.error_history[j]
            if v <= 10.0:
                col = THEME_GREEN
            elif v <= 30.0:
                col = THEME_AMBER
            else:
                col = THEME_RED
            self.plot_canvas.create_line(pts[j][0], pts[j][1], pts[j+1][0], pts[j+1][1], fill=col, width=2)

        # Label
        self.plot_canvas.create_text(4, 6, anchor=tk.NW, text="BORESIGHT (px)", fill=THEME_MUTED, font=("Segoe UI", 7))

    def _launch_plugin_playground(self) -> None:
        """Open the Plugin Playground window."""
        from .plugin_panel import PluginPlaygroundWindow
        if not hasattr(self, "_plugin_win") or self._plugin_win is None or not self._plugin_win.winfo_exists():
            self._plugin_win = PluginPlaygroundWindow(self.root)
        else:
            self._plugin_win.lift()

    def _on_close(self) -> None:
        self.is_running = False
        self.root.destroy()


def launch_gui(cfg: Optional[AppConfig] = None) -> None:
    """Launch Desktop GUI application."""
    root = tk.Tk()
    app = FSOCTrackerApp(root, cfg)
    root.mainloop()
