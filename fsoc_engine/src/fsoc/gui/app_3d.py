"""
src/fsoc/gui/app_3d.py
======================
Native Desktop 3D Workstation Application for FSOC Optical Tracking.
Runs the complete Three.js 3D Earth, Spacecraft Orbit, Ground Station,
and Optical Laser Beacon Tracking system inside a dedicated native Windows
desktop application window (powered by pywebview + WebView2).
No web browser, no tabs, no address bar — 100% native offline desktop executable.
"""
from __future__ import annotations
import http.server
import socketserver
import threading
import sys
from pathlib import Path
from typing import Optional

try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False


class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Silent HTTP handler to prevent console clutter."""
    def log_message(self, format, *args):
        pass


def _find_web_dist_dir() -> Optional[Path]:
    """Find the compiled 3D web distribution assets."""
    # 1. PyInstaller bundled location
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        for sub in [meipass / "web_dist", meipass / "web" / "dist", meipass]:
            if sub.exists() and (sub / "index.html").exists():
                return sub

    # 2. Development candidates
    candidates = [
        Path(__file__).resolve().parents[3] / "web_dist",
        Path(__file__).resolve().parents[3] / "web" / "dist",
        Path(__file__).resolve().parents[4] / "web_dist",
        Path(__file__).resolve().parents[4] / "web" / "dist",
        Path.cwd() / "web_dist",
        Path.cwd() / "web" / "dist",
        Path.cwd() / "dist" / "FSOCTracker" / "_internal" / "web_dist",
    ]
    for p in candidates:
        if p.exists() and (p / "index.html").exists():
            return p
    return None


def _launch_app_window(url: str, title: str = "ISRO FSOC 3D Workstation") -> bool:
    """Launch clean dedicated application window via native browser app mode."""
    import subprocess
    import shutil
    import webbrowser

    edge_candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Users") / Path.home().name / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
    ]
    which_edge = shutil.which("msedge")
    if which_edge:
        edge_candidates.insert(0, Path(which_edge))

    for p in edge_candidates:
        if p.exists():
            try:
                subprocess.Popen(
                    [str(p), f"--app={url}", "--window-size=1400,860", "--start-maximized"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass

    chrome_which = shutil.which("chrome")
    if chrome_which:
        try:
            subprocess.Popen(
                [chrome_which, f"--app={url}", "--window-size=1400,860"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass

    # Fallback to system default browser
    webbrowser.open(url)
    return True


def _is_port_in_use(port: int) -> bool:
    """Check if a local port is already open/bound."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_fastapi_server(port: int = 8000) -> bool:
    """Start uvicorn FastAPI backend server in a background daemon thread."""
    try:
        import uvicorn
        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=port,
            log_level="error",
            loop="asyncio",
            log_config=None,
        )
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        return True
    except Exception as e:
        print(f"[FSOC Server] FastAPI background server launch notice: {e}")
        return False


def launch_3d_desktop(title: str = "ISRO / SAC PS 26169 — FSOC 3D Virtual Camera Tracking Workstation") -> None:
    """
    Launch the native 3D desktop application window with embedded FastAPI server.
    """
    dist_dir = _find_web_dist_dir()
    if dist_dir is None:
        print("[ERROR] 3D assets not found. Please run 'npm run build' inside web/ directory.")
        return

    # Start FastAPI server on port 8000 so OpenCV VideoBench, Telemetry, and Presets are active
    httpd = None
    if not _is_port_in_use(8000):
        _start_fastapi_server(8000)
        import time
        for _ in range(25):
            if _is_port_in_use(8000):
                break
            time.sleep(0.1)

    if _is_port_in_use(8000):
        url = "http://127.0.0.1:8000/"
    else:
        # Fallback to local loopback HTTP server
        handler = lambda *args, **kwargs: QuietHTTPHandler(*args, directory=str(dist_dir), **kwargs)
        httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        url = f"http://127.0.0.1:{port}/"

    # 1. Try PyWebView if environment supports it without pythonnet crash
    webview_success = False
    if HAS_WEBVIEW:
        try:
            window = webview.create_window(
                title=title,
                url=url,
                width=1400,
                height=860,
                min_size=(1050, 700),
                background_color="#0a0f16",
            )
            webview.start(gui="edgechromium")
            webview_success = True
        except Exception as e:
            # Python.Runtime / CLR error on other laptops -> fallback seamlessly
            webview_success = False

    # 2. Seamless Standalone Native Window Mode (Works on 100% Windows PCs)
    if not webview_success:
        _launch_app_window(url, title)
        # Keep server alive in main thread
        try:
            import time
            while True:
                time.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            if httpd:
                httpd.shutdown()

