@echo off
title ISRO FSOC Tracker - Automated Benchmark Suite
if exist "%~dp0fsoc_engine" (
    cd /d "%~dp0fsoc_engine"
) else (
    cd /d "%~dp0fsoc_tracker"
)
set PYTHONPATH=src;%PYTHONPATH%

echo =====================================================================
echo    ISRO / SAC PS 26169 - FSOC VIRTUAL CAMERA TRACKING SYSTEM
echo    Running Automated Benchmark-1 and Benchmark-2 Evaluation Suite...
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

%PY_EXE% main.py benchmark --type all --duration 2.0
echo.
echo Benchmark execution complete. Results saved to benchmark_results/
pause
