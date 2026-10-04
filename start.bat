@echo off
chcp 65001 >nul
title AI_Diag_UZ Bot - Usta
cd /d "%~dp0"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

echo.
echo ============================================================
echo   AI_Diag_UZ - Usta  CarDiag UZ Bot
echo ============================================================
echo   Web-panel: http://localhost:8080
echo   Stop: Ctrl+C
echo ============================================================
echo.

REM Clear Python cache to prevent stale .pyc files
if exist __pycache__ (
    echo Clearing Python cache...
    rd /s /q __pycache__
    echo Cache cleared OK
) else (
    echo Cache: clean
)

REM Run auth_telethon.py every time.
REM If session is valid - exits in 1-2 sec without questions.
REM If session missing or broken - runs interactive auth.
python auth_telethon.py
if errorlevel 1 (
    echo.
    echo WARNING: Telethon auth incomplete.
    echo Files larger than 20MB cannot be downloaded automatically.
    echo Run start.bat again to retry authorization.
    echo.
)

python main.py

echo.
echo Bot stopped.
pause
