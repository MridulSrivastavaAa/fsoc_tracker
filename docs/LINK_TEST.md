# Post-Publish Link & Artifact Integrity Test Procedure

After publishing the GitHub release for NETRA, follow this standard procedure to verify that all download links, mirrors, and artifact signatures are publicly accessible and uncorrupted.

---

## 1. Incognito Download Test

1. Open a new **Private / Incognito** browser window (ensuring no active GitHub authentication sessions or cached credentials).
2. Navigate to the release page:
   ```text
   https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest
   ```
3. Test downloading the primary artifacts directly:
   - [ ] **Windows Installer:**
     `https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Setup.exe`
   - [ ] **Portable ZIP:**
     `https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/NETRA-Portable.zip`
   - [ ] **Checksums:**
     `https://github.com/MridulSrivastavaAa/fsoc_tracker/releases/latest/download/checksums.txt`
4. Confirm that all three files download without HTTP 404, 403, or redirect errors.

---

## 2. Checksum Verification

Open PowerShell in the folder where the files were downloaded and calculate the SHA-256 hashes:

```powershell
# Compare downloaded hashes against checksums.txt
Get-FileHash NETRA-Setup.exe, NETRA-Portable.zip -Algorithm SHA256 | Format-Table -AutoSize
Get-Content checksums.txt
```

Verify that the calculated SHA-256 hash matches the string in `checksums.txt` byte-for-byte.

---

## 3. Execution Smoke Test

1. On a clean Windows machine (or VM/Sandbox):
   - Double-click `NETRA-Setup.exe`
   - Confirm Inno Setup displays the installer branding
   - Complete installation and launch NETRA
2. From PowerShell, verify the frozen self-test:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\NETRA\NETRA.exe" --selftest
   ```
   Confirm output displays `[NETRA SELFTEST] PASS` and exits with code `0`.
