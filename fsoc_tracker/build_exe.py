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
    main_script = project_root / "src" / "fsoc" / "cli" / "main.py"
    config_dir = project_root / "configs"
    
    # Separator for PyInstaller --add-data (';' on Windows, ':' on Unix)
    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=FSOCTracker",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--add-data={config_dir}{sep}configs",
        f"--paths={project_root / 'src'}",
        str(main_script),
    ]

    print(f"[FSOC Tracker] Executing PyInstaller command: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print("\n[FSOC Tracker] Build successful! Standalone executable located at: dist/FSOCTracker/FSOCTracker.exe\n")


if __name__ == "__main__":
    build()
