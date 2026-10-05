# NETRA v1.0.0 — Next-Generation Emulation for Tracking & Real-Time Alignment
**By Team NavDrishti1**

NETRA (Next-Generation Emulation for Tracking & Real-Time Alignment) is an advanced, high-performance Free-Space Optical Communications (FSOC) Pointing, Acquisition, and Tracking (PAT) simulation and control workstation. It integrates multi-model closed-loop Kalman & IMM estimation, optical flow motion compensation, and deep CNN verification for reliable sub-pixel beam steering under heavy atmospheric scintillation and cloud occlusions.

---

## Downloads

| Package | File | Description |
|---|---|---|
| **Windows Installer** | [`NETRA-Setup.exe`](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Setup.exe) | Recommended: Full guided installer with desktop/start menu shortcuts and runtime checks. |
| **Portable ZIP** | [`NETRA-Portable.zip`](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Portable.zip) | Standalone portable archive. Unpack and launch `NETRA.exe` directly without installation. |
| **macOS Disk Image** | [`NETRA-macOS.dmg`](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-macOS.dmg) | Standalone macOS application bundle (.dmg). Apple Silicon (M1 or later) only. |
| **Integrity Checksums** | [`checksums.txt`](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/checksums.txt) • [`checksums-macos.txt`](https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/checksums-macos.txt) | Cryptographic SHA-256 hashes for all release artifacts. |

---

## System Requirements

- **Operating System:** 
  - Microsoft Windows 10 (version 1809+) or Windows 11 (64-bit).
  - macOS 12 (Monterey) or later (Apple Silicon M1 or later only).
- **Architecture:** x86_64 (Windows), arm64 (macOS).
- **Dependencies:** **None.** Python is not required. All runtimes, ONNX models, and computer vision libraries are self-contained.
- **Browser:** Google Chrome or Microsoft Edge is recommended for dedicated app-window mode.
- **Network:** 100% Offline operation supported. No internet connection is needed.

---

## Quick Start & Installation

### Windows
1. **Install or Extract:** Run `NETRA-Setup.exe` (or extract `NETRA-Portable.zip`).
2. **Launch:** Open `NETRA` from your Desktop or Start Menu.
3. **Execute & Analyze:** Choose an atmospheric scenario, start the simulation loop, and monitor real-time closed-loop beam telemetry.

### macOS (Apple Silicon M1 or later)
1. **Open Disk Image:** Double-click `NETRA-macOS.dmg` to mount the image.
2. **Install:** Drag `NETRA.app` into your `/Applications` folder.
3. **First Launch (Gatekeeper):** Because this build is distributed directly without an Apple Developer ID certificate:
   - Either right-click `NETRA.app` in `/Applications` ➔ click **Open** ➔ confirm **Open**;
   - Or open Terminal and run:
     ```bash
     xattr -dr com.apple.quarantine /Applications/NETRA.app
     ```
4. **Browser Mode:** Google Chrome or Microsoft Edge is recommended for native app-window mode. Reports and logs are saved to `~/Library/Application Support/NETRA/`.

---

## Windows SmartScreen Notice

Since this is a fresh release without an enterprise EV certificate, Windows SmartScreen may present a warning dialog stating *"Windows protected your PC"*.
- Click **"More info"**
- Click **"Run anyway"** to launch.

---

## Performance Reports & Data Storage

All auto-generated performance metrics, CSV runs, JSON logs, and benchmark reports are safely stored outside the read-only installation directory at:
```text
%APPDATA%\NETRA\reports\
```
To run the automated verification suite from the terminal:
```powershell
.\NETRA.exe --selftest
```

---

## Checksums (SHA-256)

```text
[SHA-256 Checksums will be generated automatically upon running build_release.bat]
NETRA-Setup.exe:     <BUILD_ARTIFACT_SHA256>
NETRA-Portable.zip:  <BUILD_ARTIFACT_SHA256>
```

---

## Documentation & Resources

- [User Manual & Documentation](https://github.com/MridulSrivastavaAa/fsoc_tracker#readme)
- [Video Demonstration](https://github.com/MridulSrivastavaAa/fsoc_tracker/blob/main/docs/demo.mp4) (Placeholder)
- [Clean-Machine Verification Checklist](https://github.com/MridulSrivastavaAa/fsoc_tracker/blob/main/docs/RELEASE_CHECKLIST.md)
