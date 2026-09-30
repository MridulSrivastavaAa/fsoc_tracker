"""
build_exe.py
============
Standalone Executable Packaging Script for FSOC Tracker (PyInstaller).
Bundles:
- Complete Python source code
- OpenCV, ONNX Runtime, NumPy, SciPy, Pillow
- YAML configurations in configs/
- Trained ONNX model in models/
Outputs: dist/FSOCTracker.exe
"""
import sys
import subprocess
from pathlib import Path


def build():
    print("[FSOC Tracker] Initiating Standalone .EXE Build Process...")

    # Ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("[FSOC Tracker] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    project_root = Path(__file__).resolve().parent
    main_script = project_root / "launcher.py"
    config_dir = project_root / "configs"
    src_dir = project_root / "src"
    
    # Separator for PyInstaller --add-data (';' on Windows, ':' on Unix)
    sep = ";" if sys.platform == "win32" else ":"

    models_dir = project_root / "models"
    web_dist_dir = project_root / "web_dist"

    # Copy latest web/dist build to web_dist if present
    source_web_dist = project_root.parent / "web" / "dist"
    if not source_web_dist.exists():
        source_web_dist = project_root / "web" / "dist"
    if source_web_dist.exists():
        import shutil
        if web_dist_dir.exists():
            shutil.rmtree(web_dist_dir)
        shutil.copytree(source_web_dist, web_dist_dir)
        print(f"[FSOC Tracker] Synced latest 3D web UI build from {source_web_dist} -> {web_dist_dir}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=FSOCTracker",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--add-data={config_dir}{sep}configs",
        f"--add-data={models_dir}{sep}models",
        f"--add-data={web_dist_dir}{sep}web_dist",
        f"--add-data={src_dir}{sep}src",
        "--hidden-import=webview",
        "--hidden-import=bottle",
        "--hidden-import=pythonnet",
        "--hidden-import=clr",
        f"--paths={src_dir}",
        str(main_script),
    ]

    print(f"[FSOC Tracker] Executing PyInstaller command: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print("\n[FSOC Tracker] Build successful! Standalone executable located at: dist/FSOCTracker/FSOCTracker.exe\n")


if __name__ == "__main__":
    build()
