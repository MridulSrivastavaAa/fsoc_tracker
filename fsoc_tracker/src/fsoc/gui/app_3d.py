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
    candidates = [
        Path(__file__).resolve().parents[3] / "web_dist",
        Path(__file__).resolve().parents[3] / "web" / "dist",
        Path(__file__).resolve().parents[4] / "web_dist",
        Path(__file__).resolve().parents[4] / "web" / "dist",
        Path.cwd() / "web_dist",
        Path.cwd() / "web" / "dist",
    ]
    for p in candidates:
        if p.exists() and (p / "index.html").exists():
            return p
    return None


def launch_3d_desktop(title: str = "ISRO / SAC PS 26169 — FSOC 3D Virtual Camera Tracking Workstation") -> None:
    """
    Launch the native 3D desktop application window.
    """
    dist_dir = _find_web_dist_dir()
    if dist_dir is None:
        print("[ERROR] 3D assets not found. Please run 'npm run build' inside web/ directory.")
        return

    # Start loopback HTTP server on random free port
    handler = lambda *args, **kwargs: QuietHTTPHandler(*args, directory=str(dist_dir), **kwargs)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"

    if HAS_WEBVIEW:
        # Native Desktop Application Window
        window = webview.create_window(
            title=title,
            url=url,
            width=1400,
            height=860,
            min_size=(1050, 700),
            background_color="#0a0f16",
        )
        try:
            webview.start()
        finally:
            httpd.shutdown()
    else:
        # Fallback to local desktop viewer if pywebview is missing
        import webbrowser
        print(f"[INFO] Opening 3D Workstation at {url}")
        webbrowser.open(url)
