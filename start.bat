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

REM Check if Telethon auth is needed
python -c "import os,sys;sys.path.insert(0,r'%~dp0');f=open(r'%~dp0config.py');t=f.read();f.close();sys.exit(0 if 'TG_API_ID' not in t or '= 0' in t else (0 if os.path.exists(r'%~dp0bot_session.session') else 1))" >nul 2>&1
if errorlevel 1 (
    echo Telethon auth required...
    echo.
    python auth_telethon.py
    echo.
)

python main.py

echo.
echo Bot stopped.
pause
