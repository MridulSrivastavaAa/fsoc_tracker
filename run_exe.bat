@echo off
title NETRA - ISRO FSOC 3D Tracker Workstation
cd /d "%~dp0dist\FSOCTracker"

echo =====================================================================
echo    NETRA: AI-Based Virtual Camera Tracking System (ISRO PS 26169)
echo    Launching Native Standalone Executable (FSOCTracker.exe)...
echo =====================================================================
echo.

start "" "FSOCTracker.exe"
exit
