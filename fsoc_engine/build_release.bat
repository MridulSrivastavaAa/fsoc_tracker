@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo  NETRA FSOC PAT Workstation - Standalone Windows Release Builder
echo =====================================================================
echo.

:: 1. Read Version from fsoc/__version__.py
set VERSION=1.0.0
for /f "delims=" %%a in ('python -c "exec(open('src/fsoc/__version__.py').read()); print(VERSION)" 2^>nul') do (
    set VERSION=%%a
)
echo Target Release Version: %VERSION%
echo.

:: Detect Inno Setup Compiler
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
)
if not exist %ISCC% (
    set ISCC=ISCC.exe
)

:: Step 1/5: Branding Artwork
echo [1/5] Generating icon, splash, and installer artwork...
python make_icon.py
if errorlevel 1 goto :fail_art

:: Step 2/5: PyInstaller Onedir Build
echo.
echo [2/5] Building standalone executable with PyInstaller...
pyinstaller NETRA.spec --noconfirm --clean
if errorlevel 1 goto :fail_pyi

:: Step 3/5: Portable ZIP
echo.
echo [3/5] Packaging portable ZIP (release\NETRA-Portable.zip)...
if not exist release mkdir release
if exist release\NETRA-Portable.zip del /f /q release\NETRA-Portable.zip
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path dist\NETRA\* -DestinationPath release\NETRA-Portable.zip -Force"
if errorlevel 1 goto :fail_zip

:: Step 4/5: Inno Setup Installer
echo.
echo [4/5] Compiling Inno Setup installer wizard...
%ISCC% /DAppVersion=%VERSION% installer.iss
if errorlevel 1 (
    echo.
    echo [WARNING] Inno Setup compiler (ISCC.exe) failed or was not found.
    echo If Inno Setup 6 is not installed, download it from https://jrsoftware.org/isdl.php
    echo and compile installer.iss manually.
    goto :fail_iscc
)

:: Step 5/5: Checksums
echo.
echo [5/5] Generating SHA-256 release checksums...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path release\*.exe, release\*.zip | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash + '  ' + $_.Name } | Set-Content release\checksums.txt -Encoding ascii"
if errorlevel 1 goto :fail_hash

echo.
echo =====================================================================
echo  BUILD SUCCESSFUL!
echo =====================================================================
echo Output artifacts in release\:
dir release
echo.
echo Checksums:
type release\checksums.txt
echo =====================================================================
exit /b 0

:fail_art
echo.
echo [ERROR] Failed at Step 1: Branding artwork generation.
exit /b 1

:fail_pyi
echo.
echo [ERROR] Failed at Step 2: PyInstaller executable freeze.
exit /b 1

:fail_zip
echo.
echo [ERROR] Failed at Step 3: Portable ZIP archive creation.
exit /b 1

:fail_iscc
echo.
echo [ERROR] Failed at Step 4: Inno Setup compilation.
exit /b 1

:fail_hash
echo.
echo [ERROR] Failed at Step 5: Checksum generation.
exit /b 1
