@echo off
title ISRO FSOC 3D - Full Stack Launcher
color 0B

echo =====================================================================
echo    ISRO / SAC PS 26169 - FSOC 3D VIRTUAL CAMERA TRACKING SYSTEM
echo    Starting FastAPI Backend + React Frontend
echo =====================================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PY_EXE=python
) else (
    if exist "%USERPROFILE%\python311\python.exe" (
        set PY_EXE="%USERPROFILE%\python311\python.exe"
    ) else (
        set PY_EXE=python
    )
)

echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
start "FSOC FastAPI Backend" cmd /k "cd /d "%~dp0fsoc_engine\src" && %PY_EXE% -m uvicorn fsoc.server.app:app --host 0.0.0.0 --port 8000"

echo Waiting for FastAPI to start (5 seconds)...
timeout /t 5 /nobreak > nul

echo [2/2] Starting React Frontend on http://localhost:5173 ...
start "FSOC Web Frontend" cmd /k "cd /d "%~dp0web" && npm run dev -- --open"

echo.
echo =====================================================================
echo    Both servers are starting!
echo    Backend:  http://localhost:8000  (FastAPI / WebSocket)
echo    Frontend: http://localhost:5173  (React + Vite)
echo.
echo    The UI will auto-connect to the backend.
echo    If "Remote engine disconnected" shows, click Connect in the UI.
echo =====================================================================
echo.
pause
