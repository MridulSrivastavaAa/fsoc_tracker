"""
src/fsoc/__main__.py
====================
Enables running `python -m fsoc <command>` directly.
"""
import sys
from .cli.main import main

if __name__ == "__main__":
    sys.exit(main())
