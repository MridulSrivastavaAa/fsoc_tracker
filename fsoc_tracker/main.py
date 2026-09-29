"""
main.py
=======
Root entry point for FSOC Virtual Camera Tracking System.
Usage:
  python main.py gui
  python main.py benchmark --type all
  python main.py run --duration 5.0
"""
import sys
from pathlib import Path

# Automatically add src/ to Python module search path
_src_path = Path(__file__).resolve().parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from fsoc.cli.main import main

if __name__ == "__main__":
    # If no arguments provided, default to launching GUI
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    sys.exit(main())
