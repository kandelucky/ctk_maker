@echo off
title CTkMaker
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo ============================================
    echo App exited with an error. See output above.
    echo ============================================
    pause
)
