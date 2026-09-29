@echo off
title ISRO FSOC Tracker - Operator Workstation
cd /d "%~dp0"
set PYTHONPATH=src;%PYTHONPATH%

echo =====================================================================
echo    ISRO / SAC PS 26169 - FSOC VIRTUAL CAMERA TRACKING SYSTEM
echo    Launching Interactive Desktop Telemetry Workstation (GUI)...
echo =====================================================================
echo.

python main.py gui

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
)
pause
