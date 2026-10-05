"""
src/fsoc/paths.py
=================
Canonical path helpers for the NETRA FSOC PAT Workstation.

Provides two categories of paths:
  * Read-only bundled resources (model weights, web assets, presets)
    → resource_path(rel): works both from source and from a frozen PyInstaller build
  * Writable user-data directories (reports, logs, plugins)
    → data_dir(), reports_dir(), logs_dir(), plugins_dir()
    All writable directories are created on first call.

The writable root is chosen (in order of priority):
  1. $NETRA_DATA_DIR  – test / CI override
  2. %APPDATA%\\NETRA  – Windows production
  3. ~/NETRA          – fallback (macOS/Linux dev)
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Read-only resources (bundled assets, model weights, web_dist)
# ---------------------------------------------------------------------------

def resource_path(rel: str) -> Path:
    """
    Return the absolute path to a bundled read-only resource.

    When running from source:
        base = <fsoc_engine dir>  (two levels above this file: src/fsoc → src → fsoc_engine)
    When running frozen (PyInstaller --onedir):
        base = sys._MEIPASS  (the _internal extraction folder next to the exe)

    Args:
        rel: Relative path string, e.g. "models/beacon_verifier.onnx" or "web_dist/index.html"

    Returns:
        Absolute Path object.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        # From source: this file lives at src/fsoc/paths.py
        # Go up two directories to reach fsoc_engine/
        base = Path(__file__).resolve().parents[2]
    return base / rel


# ---------------------------------------------------------------------------
# Writable user-data root
# ---------------------------------------------------------------------------

def _data_root() -> Path:
    """Return the user-writable data root, honouring NETRA_DATA_DIR override."""
    override = os.environ.get("NETRA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    # macOS: ~/Library/Application Support/NETRA
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "NETRA"
    # Windows: %APPDATA%\NETRA
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "NETRA"
    # Linux / other fallback
    return Path.home() / ".local" / "share" / "NETRA"


def data_dir() -> Path:
    """Return (and create) the top-level user-writable data directory."""
    p = _data_root()
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    """Return (and create) user reports directory."""
    p = _data_root() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    """Return (and create) user logs directory."""
    p = _data_root() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def plugins_dir() -> Path:
    """Return (and create) user plugins directory."""
    p = _data_root() / "plugins"
    p.mkdir(parents=True, exist_ok=True)
    return p


def open_reports_folder(folder: Path | str | None = None) -> None:
    """
    Open the reports folder (or specified folder) in the native file manager:
      * Windows: os.startfile
      * macOS:   open <path>
      * Linux:   xdg-open <path>
    """
    target = Path(folder) if folder is not None else reports_dir()
    target.mkdir(parents=True, exist_ok=True)
    target_str = str(target)

    if sys.platform == "win32":
        os.startfile(target_str)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", target_str])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", target_str])

