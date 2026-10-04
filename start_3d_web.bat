@echo off
title NETRA - Interactive Web Mission Control
cd /d "%~dp0web"

echo =====================================================================
echo    NETRA - AI-BASED VIRTUAL CAMERA TRACKING SYSTEM (PS 26169)
echo    Launching Interactive 3D Web Visualizer & Orbit Tracker...
echo =====================================================================
echo.
echo Starting local web server... (Press Ctrl+C to stop)
echo Open in browser: http://localhost:5173
echo.

npm run dev -- --open

pause
