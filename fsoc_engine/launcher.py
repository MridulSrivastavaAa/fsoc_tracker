"""
launcher.py
===========
Frozen-safe entry point for the NETRA FSOC PAT Workstation.

Handles:
  - Safe stream redirection for windowed executables (sys.stdout/stderr -> netra.log)
  - multiprocessing.freeze_support() for PyInstaller --onedir
  - Windows AppUserModelID for correct taskbar grouping
  - NETRA_DATA_DIR and NETRA_ASSETS_DIR environment setup
  - PyInstaller splash screen updates (graceful no-op if not present)
  - --selftest flag: 60-frame headless smoke test, writes KPI report, exits 0/1
  - --playground flag: opens Plugin Playground Tkinter window directly
  - Comprehensive startup crash guard: writes traceback to netra.log / crash.log
    and displays a native Tkinter error dialog with the log path

Usage (source):
  python launcher.py           → launches 3D workstation (default)
  python launcher.py --selftest
  python launcher.py --playground

Usage (frozen):
  NETRA.exe                    → launches 3D workstation
  NETRA.exe --selftest
  NETRA.exe --playground
"""
import io
import multiprocessing
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Stream redirection (MUST happen before importing anything that logs)
# ---------------------------------------------------------------------------

_LOG_FILE: Path | None = None


def _get_log_dir() -> Path:
    """Resolve writable log directory outside of read-only install directory."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / "NETRA" if appdata else Path.home() / "AppData" / "Roaming" / "NETRA"
    else:
        base = Path.home() / "NETRA"
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


class _TeeStream:
    """Tee output to both a log file and an active console (if available)."""

    def __init__(self, file_stream, console_stream=None) -> None:
        self.file_stream = file_stream
        self.console_stream = console_stream

    def write(self, data: str) -> int:
        n = 0
        try:
            n = self.file_stream.write(data)
            self.file_stream.flush()
        except Exception:
            pass
        if self.console_stream is not None:
            try:
                self.console_stream.write(data)
                self.console_stream.flush()
            except Exception:
                pass
        return n

    def flush(self) -> None:
        try:
            self.file_stream.flush()
        except Exception:
            pass
        if self.console_stream is not None:
            try:
                self.console_stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        if self.console_stream is not None and hasattr(self.console_stream, "isatty"):
            try:
                return self.console_stream.isatty()
            except Exception:
                return False
        return False


def _redirect_streams_if_frozen() -> None:
    """
    With PyInstaller console=False, sys.stdout and sys.stderr are None on Windows.
    Redirect both to %APPDATA%/NETRA/logs/netra.log (line-buffered, UTF-8)
    BEFORE importing any module that initializes logging.
    """
    global _LOG_FILE
    try:
        log_dir = _get_log_dir()
        _LOG_FILE = log_dir / "netra.log"
        log_stream = open(_LOG_FILE, "a", buffering=1, encoding="utf-8", errors="replace")

        if getattr(sys, "frozen", False):
            console_out = None
            if sys.platform == "win32":
                try:
                    import ctypes
                    # Attach to parent console if launched from cmd or PowerShell
                    if ctypes.windll.kernel32.AttachConsole(-1) != 0:
                        console_out = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                except Exception:
                    pass
            elif sys.stdout is not None:
                console_out = sys.stdout

            if console_out is not None:
                sys.stdout = _TeeStream(log_stream, console_out)
                sys.stderr = _TeeStream(log_stream, console_out)
            else:
                sys.stdout = log_stream
                sys.stderr = log_stream
        else:
            # Running from source: fallback if stdout/stderr happen to be None
            if sys.stdout is None:
                sys.stdout = log_stream
            if sys.stderr is None:
                sys.stderr = log_stream
    except Exception:
        # Ultimate fallback: keep streams valid to prevent AttributeError
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()


_redirect_streams_if_frozen()


# ---------------------------------------------------------------------------
# Path bootstrap (must happen before any fsoc imports)
# ---------------------------------------------------------------------------

def _bootstrap_paths() -> None:
    """Add src/ to sys.path both from source and from a frozen build."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        for candidate in [meipass / "src", meipass]:
            s = str(candidate)
            if candidate.exists() and s not in sys.path:
                sys.path.insert(0, s)
    else:
        src = Path(__file__).resolve().parent / "src"
        if src.exists() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
        # Also keep fsoc_engine root on path for compat
        root = Path(__file__).resolve().parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))


_bootstrap_paths()


# ---------------------------------------------------------------------------
# Splash helper (no-op when not frozen or splash IPC not present)
# ---------------------------------------------------------------------------

def _splash(msg: str) -> None:
    if "_PYI_SPLASH_IPC" not in os.environ:
        return
    try:
        import pyi_splash  # type: ignore[import]
        if pyi_splash.is_alive():
            pyi_splash.update_text(msg)
    except BaseException:
        pass


def _close_splash() -> None:
    if "_PYI_SPLASH_IPC" not in os.environ:
        return
    try:
        import pyi_splash  # type: ignore[import]
        if pyi_splash.is_alive():
            pyi_splash.close()
    except BaseException:
        pass


# ---------------------------------------------------------------------------
# Main & Error Handling
# ---------------------------------------------------------------------------

def main() -> int:
    multiprocessing.freeze_support()

    # Windows taskbar grouping
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "TeamNETRA.FSOC.PAT.1"
            )
        except Exception:
            pass

    # Set up user-data directories and expose them as env vars so sub-modules
    # can read them without importing paths.py (avoids bootstrap ordering issues).
    try:
        from fsoc.paths import data_dir, reports_dir, logs_dir, plugins_dir, resource_path
        _data = data_dir()
        os.environ.setdefault("NETRA_DATA_DIR", str(_data))
        os.environ.setdefault("NETRA_ASSETS_DIR", str(resource_path("assets")))
        # Pre-create all sub-dirs
        reports_dir()
        logs_dir()
        plugins_dir()
    except Exception as exc:
        _fallback = _get_log_dir().parent
        _fallback.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("NETRA_DATA_DIR", str(_fallback))

    # --selftest / --playground flags (handled before GUI init for fast exit)
    args = sys.argv[1:]
    if "--selftest" in args or "selftest" in args:
        _splash("Running selftest...")
        _close_splash()
        from fsoc.cli.main import cmd_selftest
        return cmd_selftest()

    if "--playground" in args or "playground" in args:
        _close_splash()
        from fsoc.cli.main import cmd_playground
        return cmd_playground()

    # Normal GUI launch
    _splash("Loading NETRA detection models...")
    try:
        from fsoc.cli.main import main as cli_main
        _splash("Starting NETRA workstation...")
        _close_splash()
        return cli_main(["gui", "--mode", "3d"])
    except Exception as exc:
        import traceback
        _close_splash()
        tb = traceback.format_exc()

        # Write crash traceback to log file
        log_dir = _get_log_dir()
        crash_file = log_dir / "crash.log"
        netra_log = log_dir / "netra.log"

        try:
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass

        try:
            with open(netra_log, "a", encoding="utf-8") as f:
                f.write(f"\n[STARTUP CRASH] {exc}\n{tb}\n")
        except Exception:
            pass

        # Show native Tkinter error dialog with the log file path
        try:
            import tkinter as tk
            from tkinter import messagebox
            _root = tk.Tk()
            _root.withdraw()
            messagebox.showerror(
                "NETRA — Startup Error",
                f"The application encountered an error during startup.\n\n"
                f"Crash Log: {crash_file}\n"
                f"Diagnostic Log: {netra_log}\n\n"
                f"Error: {exc}"
            )
            _root.destroy()
        except Exception:
            try:
                sys.stderr.write(f"[NETRA] FATAL: {exc}\n{tb}\n")
            except Exception:
                pass

        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _fatal:
        import traceback
        _tb = traceback.format_exc()
        try:
            _ld = _get_log_dir()
            with open(_ld / "crash.log", "w", encoding="utf-8") as _f:
                _f.write(_tb)
            with open(_ld / "netra.log", "a", encoding="utf-8") as _f:
                _f.write(f"\n[FATAL UNHANDLED] {_fatal}\n{_tb}\n")
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showerror("NETRA — Fatal Error", f"Fatal startup crash:\n\n{_fatal}\n\nSee logs in %APPDATA%\\NETRA\\logs")
            _r.destroy()
        except Exception:
            pass
        sys.exit(1)
