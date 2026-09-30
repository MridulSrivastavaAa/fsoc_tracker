@echo off
title ISRO FSOC Tracker - Automated Benchmark Suite
cd /d "%~dp0fsoc_engine"
set PYTHONPATH=src;%PYTHONPATH%

echo =====================================================================
echo    ISRO / SAC PS 26169 - FSOC VIRTUAL CAMERA TRACKING SYSTEM
echo    Running Automated Benchmark-1 and Benchmark-2 Evaluation Suite...
echo =====================================================================
echo.

python main.py benchmark --type all --duration 2.0

echo.
echo Benchmark execution complete. Results saved to benchmark_results/
pause
