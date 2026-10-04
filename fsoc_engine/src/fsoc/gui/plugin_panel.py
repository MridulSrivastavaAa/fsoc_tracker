"""
Plugin Playground GUI Panel for Tkinter desktop application.
Provides interactive algorithm swapping, custom Python code editing, auto-slider extraction,
and A/B comparison trigger.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import re
import threading
from typing import Optional, Callable, Dict, Any
import urllib.request
import json
import inspect
import math
import numpy as np

IS_STANDALONE = False

from ..plugins.registry import registry, SLOTS
from ..plugins.contracts import (
    VISION_TEMPLATE,
    TRACKING_TEMPLATE,
    CONTROL_TEMPLATE,
    VISION_CONTRACT_DOC,
    TRACKING_CONTRACT_DOC,
    CONTROL_CONTRACT_DOC,
)
from ..plugins.presets import PRESET_CATALOG
from ..plugins.ab_runner import run_ab_comparison, SCENARIOS


THEME_BG = "#0b132b"
THEME_PANEL = "#1c2541"
THEME_TEXT = "#ffffff"
THEME_ACCENT = "#48cae4"
THEME_GREEN = "#00f5d4"
THEME_ORANGE = "#ff9f1c"
THEME_RED = "#ff0054"
FONT_FAMILY = "Segoe UI"


class PluginPlaygroundWindow(tk.Toplevel):
    """
    Dedicated Toplevel window for the NETRA Plugin Playground.
    Allows researchers to select presets, write custom code, tweak parameters, and run A/B benchmarks.
    """

    def __init__(self, parent: tk.Tk, engine_callback: Optional[Callable] = None) -> None:
        super().__init__(parent)
        self.title("⚡ NETRA Algorithm Plugin Playground")
        self.geometry("900x720")
        self.configure(bg=THEME_BG)
        self.transient(parent)

        self.engine_callback = engine_callback
        self.current_slot = "tracking"
        self.slider_vars: Dict[str, tk.DoubleVar] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        # Header title banner
        header = tk.Frame(self, bg=THEME_PANEL, height=50)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header,
            text="⚡ NETRA ALGORITHM PLUGIN PLAYGROUND",
            font=(FONT_FAMILY, 14, "bold"),
            bg=THEME_PANEL,
            fg=THEME_ACCENT,
        )
        title_lbl.pack(side=tk.LEFT, padx=15, pady=10)

        # Slot selector Notebook tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_frames = {}
        for slot in SLOTS:
            tab = tk.Frame(self.notebook, bg=THEME_BG)
            self.notebook.add(tab, text=f"  {slot.upper()} SLOT  ")
            self.tab_frames[slot] = tab

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Main content container (Left: Controls & Sliders, Right: Code Editor & Docs)
        self.main_split = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=THEME_BG, sashwidth=6)
        self.main_split.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left Column: Presets, Params, Status
        self.left_col = tk.Frame(self.main_split, bg=THEME_PANEL, width=320)
        self.main_split.add(self.left_col)

        # Right Column: Code Editor & Contract Reference
        self.right_col = tk.Frame(self.main_split, bg=THEME_PANEL)
        self.main_split.add(self.right_col)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        # 1. Preset Selector Frame
        preset_frame = tk.LabelFrame(
            self.left_col, text=" Select Algorithm Preset ", bg=THEME_PANEL, fg=THEME_TEXT, font=(FONT_FAMILY, 10, "bold")
        )
        preset_frame.pack(fill=tk.X, padx=10, pady=10)

        self.preset_var = tk.StringVar(value="NETRA Default (IMM)")
        self.preset_combo = ttk.Combobox(
            preset_frame, textvariable=self.preset_var, state="readonly", font=(FONT_FAMILY, 9)
        )
        self.preset_combo.pack(fill=tk.X, padx=10, pady=8)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # 2. Tunable Parameters Frame
        self.params_frame = tk.LabelFrame(
            self.left_col, text=" Tunable Parameters (Auto-Sliders) ", bg=THEME_PANEL, fg=THEME_TEXT, font=(FONT_FAMILY, 10, "bold")
        )
        self.params_frame.pack(fill=tk.X, padx=10, pady=5)
        self.sliders_container = tk.Frame(self.params_frame, bg=THEME_PANEL)
        self.sliders_container.pack(fill=tk.X, padx=5, pady=5)

        # 3. Action Buttons Frame
        btn_frame = tk.Frame(self.left_col, bg=THEME_PANEL)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.btn_activate = tk.Button(
            btn_frame,
            text="▶ Activate Plugin",
            bg="#2a9d8f",
            fg=THEME_TEXT,
            font=(FONT_FAMILY, 10, "bold"),
            command=self._activate_plugin,
        )
        self.btn_activate.pack(fill=tk.X, pady=4)

        self.btn_ab = tk.Button(
            btn_frame,
            text="📊 Activate & Run A/B Comparison",
            bg="#e76f51",
            fg=THEME_TEXT,
            font=(FONT_FAMILY, 10, "bold"),
            command=self._run_ab_benchmark,
        )
        self.btn_ab.pack(fill=tk.X, pady=4)

        self.btn_reset = tk.Button(
            btn_frame,
            text="🔄 Reset Slot to NETRA Default",
            bg="#3d5a80",
            fg=THEME_TEXT,
            font=(FONT_FAMILY, 9),
            command=self._reset_slot,
        )
        self.btn_reset.pack(fill=tk.X, pady=4)

        # 4. Status Monitor Box
        status_frame = tk.LabelFrame(
            self.left_col, text=" Live Execution Status ", bg=THEME_PANEL, fg=THEME_TEXT, font=(FONT_FAMILY, 9, "bold")
        )
        status_frame.pack(fill=tk.X, padx=10, pady=10)

        self.lbl_status = tk.Label(
            status_frame,
            text="Status: ✅ Default Active\nCalls: 0 | Errors: 0\nLatency: 0.00 ms",
            font=(FONT_FAMILY, 9),
            bg=THEME_PANEL,
            fg=THEME_GREEN,
            justify=tk.LEFT,
        )
        self.lbl_status.pack(anchor=tk.W, padx=10, pady=5)

    def _build_right_panel(self) -> None:
        # Code Editor Header & Reset Button
        header_frame = tk.Frame(self.right_col, bg=THEME_PANEL)
        header_frame.pack(fill=tk.X, padx=10, pady=5)

        lbl_code = tk.Label(
            header_frame, text=" Python Source Code (Contract Pure Function) ", bg=THEME_PANEL, fg=THEME_ACCENT, font=(FONT_FAMILY, 10, "bold")
        )
        lbl_code.pack(side=tk.LEFT)

        btn_default_contract = tk.Button(
            header_frame,
            text="↺ Reset to Default Contract",
            bg="#1e293b",
            fg=THEME_GREEN,
            font=(FONT_FAMILY, 9),
            relief=tk.FLAT,
            padx=8,
            command=self._load_default_contract,
        )
        btn_default_contract.pack(side=tk.RIGHT)

        # Code Text Box with Scrollbar
        editor_frame = tk.Frame(self.right_col, bg=THEME_PANEL)
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.code_text = tk.Text(
            editor_frame,
            wrap=tk.NONE,
            font=("Consolas", 10),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground=THEME_ACCENT,
            selectbackground="#334155",
            undo=True,
        )
        scroll_y = tk.Scrollbar(editor_frame, orient=tk.VERTICAL, command=self.code_text.yview)
        scroll_x = tk.Scrollbar(editor_frame, orient=tk.HORIZONTAL, command=self.code_text.xview)
        self.code_text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.code_text.pack(fill=tk.BOTH, expand=True)

        self.code_text.bind("<KeyRelease>", self._on_code_changed)

        # Initial populate
        self._populate_for_slot("tracking")

    def _load_default_contract(self) -> None:
        template = TRACKING_TEMPLATE if self.current_slot == "tracking" else (CONTROL_TEMPLATE if self.current_slot == "control" else VISION_TEMPLATE)
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", template)
        self._update_sliders_from_code()

    def _on_tab_changed(self, event) -> None:
        idx = self.notebook.index(self.notebook.select())
        self.current_slot = SLOTS[idx]
        self._populate_for_slot(self.current_slot)

    def _populate_for_slot(self, slot: str) -> None:
        # Populate preset catalog combobox
        presets = list(PRESET_CATALOG.get(slot, {}).keys()) + ["✏️ Write Custom Code..."]
        self.preset_combo["values"] = presets

        curr_label = registry.get_label(slot)
        if curr_label in presets:
            self.preset_var.set(curr_label)
        else:
            self.preset_var.set("✏️ Write Custom Code...")

        # Set default template code
        self._load_default_contract()

    def _on_preset_selected(self, event=None) -> None:
        preset_name = self.preset_var.get()
        slot_presets = PRESET_CATALOG.get(self.current_slot, {})

        if preset_name in slot_presets and slot_presets[preset_name] is not None:
            import inspect
            func = slot_presets[preset_name]
            code = inspect.getsource(func)
            self.code_text.delete("1.0", tk.END)
            self.code_text.insert("1.0", code)
            self._update_sliders_from_code()
        else:
            # Handles "NETRA Default ..." (whose value is None) or "✏️ Write Custom Code..."
            self._load_default_contract()

    def _on_code_changed(self, event=None) -> None:
        self._update_sliders_from_code()

    def _update_sliders_from_code(self) -> None:
        code = self.code_text.get("1.0", tk.END)
        extracted = self.extract_params(code)

        for child in self.sliders_container.winfo_children():
            child.destroy()

        self.slider_vars.clear()

        if not extracted:
            lbl_none = tk.Label(self.sliders_container, text="No tunable params.get() found in code.", bg=THEME_PANEL, fg="#94a3b8", font=(FONT_FAMILY, 9, "italic"))
            lbl_none.pack(anchor=tk.W, pady=5)
            return

        for name, default_val in extracted.items():
            f = tk.Frame(self.sliders_container, bg=THEME_PANEL)
            f.pack(fill=tk.X, pady=2)
            lbl = tk.Label(f, text=f"{name}:", bg=THEME_PANEL, fg=THEME_TEXT, width=12, anchor=tk.W, font=(FONT_FAMILY, 9))
            lbl.pack(side=tk.LEFT)

            var = tk.DoubleVar(value=default_val)
            self.slider_vars[name] = var

            name_l = name.lower()
            if name_l == "threshold":
                min_v, max_v, res = 0.0, 255.0, 1.0
            elif name_l == "alpha":
                min_v, max_v, res = 0.0, 1.0, 0.01
            elif name_l == "beta":
                min_v, max_v, res = 0.0, 0.05, 0.0005
            elif name_l == "iv" or (0 < default_val < 0.002):
                min_v, max_v, res = 0.0, max(0.002, default_val * 3.0), 0.00001
            elif name_l == "ip" or (0.002 <= default_val < 0.2):
                min_v, max_v, res = 0.0, max(0.4, default_val * 3.0), 0.001
            elif name_l in ("pp", "pv"):
                min_v, max_v, res = 0.0, max(15.0, default_val * 2.5), 0.05
            elif name_l in ("dp", "dv"):
                min_v, max_v, res = 0.0, max(40.0, default_val * 2.5), 0.1
            elif default_val <= 0.01:
                min_v, max_v, res = 0.0, max(0.05, default_val * 4.0), 0.0001
            elif default_val <= 1.0:
                min_v, max_v, res = 0.0, max(1.0, default_val * 2.5), 0.01
            elif default_val <= 20.0:
                min_v, max_v, res = 0.0, max(20.0, default_val * 2.5), 0.05
            elif default_val <= 255.0:
                min_v, max_v, res = 0.0, max(255.0, default_val * 1.5), 1.0
            else:
                min_v, max_v, res = 0.0, max(default_val * 2.5, 10.0), 0.1

            scale = tk.Scale(
                f,
                variable=var,
                from_=min_v,
                to=max_v,
                resolution=res,
                orient=tk.HORIZONTAL,
                bg=THEME_PANEL,
                fg=THEME_ACCENT,
                highlightthickness=0,
                length=140,
            )
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

            entry = tk.Entry(
                f,
                textvariable=var,
                width=8,
                bg="#0d1117",
                fg="#00f5d4",
                insertbackground="white",
                font=(FONT_FAMILY, 9),
                relief=tk.FLAT
            )
            entry.pack(side=tk.RIGHT)

    @staticmethod
    def extract_params(code: str) -> Dict[str, float]:
        pattern = r'params\.get\(\s*["\'](\w+)["\']\s*,\s*([^)]+)\)'
        found = {}
        for match in re.finditer(pattern, code):
            name = match.group(1)
            raw_val = match.group(2).strip()
            try:
                val = float(raw_val)
            except ValueError:
                val = 1.0
            found[name] = val
        return found

    def _compile_code(self) -> Optional[Callable]:
        code = self.code_text.get("1.0", tk.END)
        namespace = {"np": np, "math": math}
        try:
            exec(code, namespace)
        except Exception as e:
            messagebox.showerror("Code Compilation Error", f"Failed to compile Python code:\n\n{e}")
            return None

        func_map = {"vision": "detect", "tracking": "track", "control": "control"}
        target_name = func_map[self.current_slot]
        func = namespace.get(target_name)

        if func is None or not callable(func):
            messagebox.showerror("Contract Error", f"Function '{target_name}' not found in code.\nEnsure your code defines 'def {target_name}(...)' matching the contract.")
            return None

        return func

    def _activate_plugin(self) -> None:
        func = self._compile_code()
        if func is None:
            return

        params = {k: v.get() for k, v in self.slider_vars.items()}
        label = self.preset_var.get()
        if label == "✏️ Write Custom Code...":
            label = "Custom Code"

        if IS_STANDALONE:
            code = self.code_text.get("1.0", tk.END)
            req = urllib.request.Request(
                "http://127.0.0.1:8000/api/plugins/apply_code",
                data=json.dumps({"slot": self.current_slot, "code": code, "params": params, "label": label}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                urllib.request.urlopen(req, timeout=2.0)
                messagebox.showinfo("Plugin Swapped", f"Successfully activated '{label}' for [{self.current_slot.upper()}] slot via API!")
            except Exception as e:
                messagebox.showerror("API Error", f"Failed to send code to server: {e}")
        else:
            registry.request(self.current_slot, func, params, label)
            messagebox.showinfo("Plugin Swapped", f"Successfully activated '{label}' for [{self.current_slot.upper()}] slot!\nThe swap will take effect on the next frame boundary.")
        self._update_status()

    def _reset_slot(self) -> None:
        registry.reset_slot(self.current_slot)
        messagebox.showinfo("Slot Reset", f"[{self.current_slot.upper()}] slot reset to NETRA Default.")
        self._populate_for_slot(self.current_slot)
        self._update_status()

    def _run_ab_benchmark(self) -> None:
        func = self._compile_code()
        if func is None:
            return

        params = {k: v.get() for k, v in self.slider_vars.items()}
        label = self.preset_var.get()

        # Run comparison in background thread to avoid freezing GUI
        def worker():
            res = run_ab_comparison(
                slot=self.current_slot,
                custom_func=func,
                custom_params=params,
                custom_label=label,
                max_frames=150,
            )
            self.after(0, lambda: self._show_ab_results_popup(res))

        threading.Thread(target=worker, daemon=True).start()
        messagebox.showinfo("A/B Benchmark", "Running 150-frame headless A/B comparison in background...\nResults will pop up shortly.")

    def _show_ab_results_popup(self, res: dict) -> None:
        win = tk.Toplevel(self)
        win.title("📊 A/B Benchmark Results")
        win.geometry("550x420")
        win.configure(bg=THEME_BG)

        lbl = tk.Label(
            win,
            text=f"A/B BENCHMARK RESULTS — {res['slot'].upper()} SLOT",
            font=(FONT_FAMILY, 12, "bold"),
            bg=THEME_BG,
            fg=THEME_ACCENT,
        )
        lbl.pack(pady=10)

        txt = tk.Text(win, font=("Consolas", 10), bg="#0f172a", fg="#e2e8f0", height=15)
        txt.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        def_info = res["default"]
        cust_info = res["custom"]
        delta = res["delta"]

        report = f"""
SCENARIO: {res['scenario_id']} (Seed=42, 150 frames)
CUSTOM PLUGIN: {res['custom_label']}

METRIC                NETRA DEFAULT       CUSTOM           DELTA
------------------------------------------------------------------
RMSE Error (px):     {def_info['rmse']:<18.2f} {cust_info['rmse']:<15.2f} {delta['rmse_delta_pct']:+.1f}%
Lock Retention:      {def_info['lock_pct']:<17.1f}% {cust_info['lock_pct']:<14.1f}% {delta['lock_delta_pct']:+.1f}%
Simulation FPS:      {def_info['fps']:<18.1f} {cust_info['fps']:<15.1f} {delta['fps_delta_pct']:+.1f}%
R14 Compliance:      {'✅ PASS' if def_info['r14_pass'] else '❌ FAIL':<18} {'✅ PASS' if cust_info['r14_pass'] else '❌ FAIL'}

VERDICT:
{res['verdict']}
"""
        txt.insert("1.0", report.strip())
        txt.configure(state="disabled")

    def _update_status(self) -> None:
        st = registry.get_status(self.current_slot)
        cust = "CUSTOM" if st["is_custom"] else "DEFAULT"
        color = THEME_ORANGE if st["is_custom"] else THEME_GREEN

        text = f"Status: {cust} ({st['label']})\nCalls: {st['calls']} | Errors: {st['errors']}\nLatency: {st['timing_ms']:.2f} ms"
        if st["last_error"]:
            text += f"\nLast Error: {st['last_error']}"

        self.lbl_status.configure(text=text, fg=color)

def launch_standalone() -> None:
    """Launch the Plugin Playground independently (used by 3D Web UI)."""
    import traceback
    try:
        print("[PLUGIN PLAYGROUND] Initializing Tkinter...")
        root = tk.Tk()
        root.withdraw()  # Hide the main root window
        print("[PLUGIN PLAYGROUND] Loading Window...")
        win = PluginPlaygroundWindow(root)
        win.attributes('-topmost', True)
        win.lift()
        win.focus_force()
        # When the Toplevel is closed, destroy the root to exit the mainloop
        win.protocol("WM_DELETE_WINDOW", lambda: root.destroy())
        print("[PLUGIN PLAYGROUND] Starting Mainloop...")
        root.mainloop()
    except Exception as e:
        print(f"[PLUGIN PLAYGROUND] Error launching Tkinter in background thread: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    if "--standalone" in sys.argv:
        IS_STANDALONE = True
        launch_standalone()
