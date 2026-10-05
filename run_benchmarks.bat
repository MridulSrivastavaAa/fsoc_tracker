@echo off
title NETRA Tracker - Automated Benchmark Suite
cd /d "%~dp0fsoc_engine"
set PYTHONPATH=src;%PYTHONPATH%

echo =====================================================================
echo    NETRA - AI-BASED VIRTUAL CAMERA TRACKING SYSTEM (PS 26169)
echo    Running Automated Benchmark-1 and Benchmark-2 Evaluation Suite...
echo =====================================================================
echo.

python main.py benchmark --type all --duration 2.0

echo.
echo Benchmark execution complete. Results saved to benchmark_results/
pause
