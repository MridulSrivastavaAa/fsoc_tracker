"""
main.py (Workspace Root Launcher)
=================================
Enables running:
  python main.py gui
  python main.py benchmark --type all
directly from the root folder without needing to cd into fsoc_tracker.
"""
import os
import sys
from pathlib import Path

# Determine project paths
_root_dir = Path(__file__).resolve().parent
_fsoc_dir = _root_dir / "fsoc_tracker"
_src_dir = _fsoc_dir / "src"

# Add to path
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_fsoc_dir) not in sys.path:
    sys.path.insert(0, str(_fsoc_dir))

# Switch working directory to fsoc_tracker so relative configs load seamlessly
os.chdir(str(_fsoc_dir))

from fsoc.cli.main import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    sys.exit(main())
