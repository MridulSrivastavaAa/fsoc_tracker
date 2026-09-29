@echo off
title ISRO FSOC 3D - Interactive Web Mission Control
cd /d "%~dp0web"

echo =====================================================================
echo    ISRO / SAC PS 26169 - FSOC 3D VIRTUAL CAMERA TRACKING SYSTEM
echo    Launching Interactive 3D Web Visualizer & Orbit Tracker...
echo =====================================================================
echo.
echo Starting local web server... (Press Ctrl+C to stop)
echo Open in browser: http://localhost:5173
echo.

npm run dev -- --open

pause
