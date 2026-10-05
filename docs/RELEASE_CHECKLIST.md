# NETRA Clean-Machine Release Verification Checklist

This checklist verifies that the NETRA standalone Windows release meets all ISRO Problem Statement criteria and operates reliably on a clean host system with **no Python installed** and **no internet connection**.

---

## 1. Test Environment Requirements

- [ ] **Clean VM or Windows Sandbox** (Windows 10 21H2+ or Windows 11 64-bit)
- [ ] **No Python** installed on the host
- [ ] **Offline** (Disconnect network adapter / turn off Wi-Fi)
- [ ] **Standard User** (Non-administrator account, verify standard privilege execution)
- [ ] **Path with Spaces** (Test installation to e.g. `C:\Users\John Doe\My Tools\NETRA`)

---

## 2. Pre-Install & Installer Verification

- [ ] **Installer Integrity**: SHA-256 matches `checksums.txt`
- [ ] **SmartScreen Handling**: Documented "More info -> Run anyway" bypass works smoothly
- [ ] **Inno Setup Wizard**:
  - [ ] Welcome page displayed with clean branding
  - [ ] License agreement (`LICENSE.txt`) displayed
  - [ ] Information before install (`QUICKSTART.txt`) displayed
  - [ ] Per-user directory defaults to `%LOCALAPPDATA%\Programs\NETRA` or `{autopf}\NETRA`
  - [ ] Component selection options (Main Workstation, Plugins SDK, Samples)
  - [ ] Desktop shortcut task checkbox
  - [ ] VC++ Redistributable check (silent install if missing)
  - [ ] Finish page with "Launch NETRA now" checkbox

---

## 3. Launch & Execution

- [ ] **Launch from Start Menu**: Opens without console pop-ups or CMD windows
- [ ] **Launch from Desktop Shortcut**: Opens correctly with custom NETRA icon
- [ ] **Splash Screen**: Displays 640x360 branded splash banner during initialization
- [ ] **Application Window**:
  - [ ] Title reads: `NETRA FSOC PAT Workstation`
  - [ ] Taskbar icon displays the cyan/amber NETRA insignia
  - [ ] Window is resizable with minimum 1050x750 bounds

---

## 4. Operational Functionality (ISRO Mandatory Requirements)

- [ ] **Scenario Execution**:
  - [ ] Select atmospheric disturbance (Clear, Haze, or Cloud Occlusion)
  - [ ] Run tracking loop
- [ ] **Frame Rate**:
  - [ ] Real-time execution maintaining **>= 20 FPS** (exceeds ISRO 15-20 FPS requirement)
- [ ] **Tracking Performance**:
  - [ ] Rapid acquisition (< 1.5 s)
  - [ ] Sub-pixel tracking accuracy (RMSE <= 15 px across scenario)
  - [ ] Lock retention maintained through simulated jitter and atmospheric scintillation
- [ ] **Closed-Loop Feedback**:
  - [ ] PID/feedforward commands actively slew the virtual gimbal/steering mirror

---

## 5. Automated Performance Reports

- [ ] **Headless Verification**:
  ```powershell
  .\NETRA.exe --selftest
  ```
  - [ ] Prints PASS with exit code 0
  - [ ] Writes detailed JSON report to `%APPDATA%\NETRA\reports\`
- [ ] **Session Performance Report**:
  - [ ] Simulation duration recorded
  - [ ] Effective & mean FPS logged
  - [ ] Acquisition and re-acquisition times logged
  - [ ] Mean, max, and RMSE tracking error logged
  - [ ] Lock retention percentage logged

---

## 6. Portable ZIP Verification

- [ ] Extract `NETRA-Portable.zip` to a test directory
- [ ] Run `NETRA.exe` directly
- [ ] Verify identical behavior and report generation to `%APPDATA%\NETRA\reports\`

---

## 7. Clean Uninstall

- [ ] Run uninstaller from Start Menu or Windows Settings
- [ ] Verify program files in `{app}` are completely removed
- [ ] Verify `%APPDATA%\NETRA` is **preserved** (user reports, logs, and custom plugins intact)
- [ ] Verify desktop and Start Menu shortcuts are removed
