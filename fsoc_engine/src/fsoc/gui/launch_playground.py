"""
launch_playground.py
====================
Standalone launcher for the Algorithm Plugin Playground window.
Called as a subprocess by the FastAPI server when the 3D GUI button is clicked.
Sets up sys.path correctly before importing Tkinter-dependent code.
"""
import sys
import os
from pathlib import Path

# ── Fix the import path ──────────────────────────────────────────────────────
_this_dir = Path(__file__).resolve()
# We are at: fsoc_engine/src/fsoc/gui/launch_playground.py
# We need:   fsoc_engine/src  to be on path for `from fsoc.xxx` imports
_src_dir = _this_dir.parents[2]   # fsoc_engine/src
_engine_dir = _this_dir.parents[3] # fsoc_engine

if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_engine_dir) not in sys.path:
    sys.path.insert(0, str(_engine_dir))

# Change cwd to fsoc_engine so relative config paths resolve
os.chdir(str(_engine_dir))

# ── Now safe to import ───────────────────────────────────────────────────────
import tkinter as tk
import traceback

# Set IS_STANDALONE flag before importing plugin_panel
import fsoc.gui.plugin_panel as _pm
_pm.IS_STANDALONE = True

from fsoc.gui.plugin_panel import PluginPlaygroundWindow


def main():
    try:
        print("[PLAYGROUND LAUNCHER] Starting Tkinter root...")
        root = tk.Tk()
        root.withdraw()
        print("[PLAYGROUND LAUNCHER] Creating PluginPlaygroundWindow...")
        win = PluginPlaygroundWindow(root)
        win.attributes('-topmost', True)
        win.lift()
        win.focus_force()
        win.protocol("WM_DELETE_WINDOW", root.destroy)
        print("[PLAYGROUND LAUNCHER] Entering mainloop...")
        root.mainloop()
        print("[PLAYGROUND LAUNCHER] Window closed.")
    except Exception as e:
        print(f"[PLAYGROUND LAUNCHER] FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
