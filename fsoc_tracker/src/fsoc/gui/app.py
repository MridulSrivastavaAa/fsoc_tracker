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

        # Right Column: Controls, Disturbances & Telemetry
        right_col = tk.Frame(body, bg=THEME_BG, width=380)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(8, 0))

        # 1. Telemetry Cards Grid
        telemetry_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        telemetry_frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(telemetry_frame, text="FLIGHT TELEMETRY", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        stats_grid = tk.Frame(telemetry_frame, bg=THEME_SURFACE)
        stats_grid.pack(fill=tk.X)

        self.val_error = self._create_stat_box(stats_grid, "TRACK ERROR", "-- px", 0, 0)
        self.val_fps = self._create_stat_box(stats_grid, "LOOP FPS", "-- FPS", 0, 1)
        self.val_pan = self._create_stat_box(stats_grid, "PAN ANGLE", "0.00 deg", 1, 0)
        self.val_tilt = self._create_stat_box(stats_grid, "TILT ANGLE", "0.00 deg", 1, 1)

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

        # Atmosphere Condition
        atmo_box = tk.Frame(dist_frame, bg=THEME_SURFACE)
        atmo_box.pack(fill=tk.X, pady=(6, 0))
        tk.Label(atmo_box, text="Atmosphere:", bg=THEME_SURFACE, fg=THEME_MUTED).pack(side=tk.LEFT)
        self.combo_atmo = ttk.Combobox(atmo_box, values=["clear", "haze", "fog", "rain", "low_light"], state="readonly", width=12)
        self.combo_atmo.set("clear")
        self.combo_atmo.pack(side=tk.RIGHT)
        self.combo_atmo.bind("<<ComboboxSelected>>", self._apply_disturbances)

        # 4. Benchmark 2 Video File Selector
        video_frame = tk.Frame(right_col, bg=THEME_SURFACE, bd=1, relief=tk.SOLID, padx=10, pady=10)
        video_frame.pack(fill=tk.X, pady=6)

        tk.Label(video_frame, text="BENCHMARK-2 VIDEO BYPASS", bg=THEME_SURFACE, fg=THEME_CYAN, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        btn_video = tk.Button(video_frame, text="📂 Load .mp4 Video Feed", bg=THEME_SURFACE2, fg=THEME_TEXT, command=self._open_video_file)
        btn_video.pack(fill=tk.X, pady=2)

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
        self.reset_system()

    def _apply_disturbances(self, event=None) -> None:
        # S&P
        if self.var_sp.get():
            self.engine.disturbances.salt_pepper.enabled = True
            self.engine.disturbances.salt_pepper.density = 0.08
        else:
            self.engine.disturbances.salt_pepper.enabled = False

        # Gaussian
        if self.var_gauss.get():
            self.engine.disturbances.gaussian.enabled = True
            self.engine.disturbances.gaussian.sigma = 15.0
        else:
            self.engine.disturbances.gaussian.enabled = False

        # Atmosphere
        atmo = self.combo_atmo.get()
        self.engine.disturbances.atmosphere.set_condition(atmo, strength=0.8)

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
        self.error_history.clear()
        self.plot_canvas.delete("all")
        self.val_error.configure(text="-- px")
        self.val_fps.configure(text="-- FPS")
        self.val_pan.configure(text="0.00 deg")
        self.val_tilt.configure(text="0.00 deg")
        self.status_badge.configure(text="STATE: IDLE", bg="#1a3a21", fg=THEME_GREEN)

    def _update_ui(self, metric: FrameMetrics) -> None:
        # 1. Update text telemetry
        err_text = f"{metric.error_px:.2f} px" if metric.error_px is not None else "-- px"
        fps = 1000.0 / max(0.1, metric.proc_ms)
        self.val_error.configure(text=err_text)
        self.val_fps.configure(text=f"{fps:.1f} FPS")
        self.val_pan.configure(text=f"{metric.pan_deg:+.2f} deg")
        self.val_tilt.configure(text=f"{metric.tilt_deg:+.2f} deg")

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
        # Fetch current viewport image from camera render
        full_f = self.engine.source.next_frame()
        # Rewind 1 frame index for rendering display
        cam_vp = self.engine.camera.render(
            self.engine.source.next_frame() or full_f or self.engine.source._background
        ) if hasattr(self.engine.source, "_background") else None

        # Build composite HUD
        raw_img = cam_vp.image if cam_vp is not None else np.zeros((480, 640), dtype=np.uint8)
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

        # 4. Update rolling error plot
        if metric.error_px is not None:
            self.error_history.append(metric.error_px)
            if len(self.error_history) > self.max_history_len:
                self.error_history.pop(0)
            self._draw_error_plot()

    def _draw_error_plot(self) -> None:
        self.plot_canvas.delete("all")
        w = self.plot_canvas.winfo_width()
        h = self.plot_canvas.winfo_height()
        if w < 50 or not self.error_history:
            return

        # 10px limit red reference line
        max_y_scale = 15.0  # max 15 px vertical scale
        y_limit = h - int((10.0 / max_y_scale) * h)
        self.plot_canvas.create_line(0, y_limit, w, y_limit, fill="#e11d48", dash=(4, 4), width=1)
        self.plot_canvas.create_text(w - 30, y_limit - 6, text="10 px", fill="#e11d48", font=("Segoe UI", 7))

        # Plot data points
        dx = w / float(self.max_history_len)
        pts: list[tuple[float, float]] = []
        for i, val in enumerate(self.error_history):
            px = i * dx
            norm_val = min(val, max_y_scale) / max_y_scale
            py = h - int(norm_val * (h - 8)) - 4
            pts.append((px, py))

        for j in range(len(pts) - 1):
            col = THEME_GREEN if self.error_history[j] <= 10.0 else THEME_RED
            self.plot_canvas.create_line(pts[j][0], pts[j][1], pts[j+1][0], pts[j+1][1], fill=col, width=2)

    def _on_close(self) -> None:
        self.is_running = False
        self.root.destroy()


def launch_gui(cfg: Optional[AppConfig] = None) -> None:
    """Launch Desktop GUI application."""
    root = tk.Tk()
    app = FSOCTrackerApp(root, cfg)
    root.mainloop()
