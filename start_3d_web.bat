@echo off
title NETRA - 3D Web Mission Control & FastAPI Engine
color 0B

echo =====================================================================
echo    NETRA - AI-BASED VIRTUAL CAMERA TRACKING SYSTEM (PS 26169)
echo    Starting FastAPI Engine + Interactive 3D Web Visualizer...
echo =====================================================================
echo.

:: Check if port 8000 is already active
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
    start "NETRA FastAPI Backend" cmd /k "cd /d "%~dp0fsoc_engine\src" && python -m uvicorn fsoc.server.app:app --host 0.0.0.0 --port 8000 --ws-ping-interval 300 --ws-ping-timeout 300"
    timeout /t 3 /nobreak > nul
) else (
    echo [1/2] FastAPI Backend is already running on port 8000.
)

echo [2/2] Starting React 3D Web Frontend on http://localhost:5173 ...
cd /d "%~dp0web"
npm run dev -- --open

pause
