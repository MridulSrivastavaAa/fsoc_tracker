"""
src/fsoc/cli/__main__.py
========================
Enables running `python -m fsoc.cli <command>`.
"""
import sys
from .main import main

if __name__ == "__main__":
    sys.exit(main())
