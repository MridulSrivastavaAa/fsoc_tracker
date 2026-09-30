"""
launcher.py
===========
Top-level entry point for PyInstaller standalone executable.
Ensures proper sys.path resolution and launches the 3D Tracking Workstation.
"""
import sys
from pathlib import Path

# Add src to sys.path
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Support PyInstaller internal path
if hasattr(sys, "_MEIPASS"):
    meipass_src = Path(sys._MEIPASS) / "src"
    if meipass_src.exists() and str(meipass_src) not in sys.path:
        sys.path.insert(0, str(meipass_src))
    if str(sys._MEIPASS) not in sys.path:
        sys.path.insert(0, str(sys._MEIPASS))

from fsoc.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
