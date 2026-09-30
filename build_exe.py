"""
build_exe.py (Root Launcher)
============================
Executes standalone .exe packaging for FSOC Tracker.
Outputs: fsoc_engine/dist/FSOCTracker/FSOCTracker.exe
"""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    fsoc_dir = Path(__file__).resolve().parent / "fsoc_engine"
    script = fsoc_dir / "build_exe.py"
    subprocess.check_call([sys.executable, str(script)], cwd=str(fsoc_dir))
