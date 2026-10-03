@echo off
chcp 65001 >nul
title Install AI_Diag_UZ Bot

echo.
echo ============================================================
echo   AI_Diag_UZ Bot - Ustanovka zavisimostey
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/4] Proverka Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo OSHIBKA: Python ne naiden!
    echo Skayte Python s https://www.python.org/downloads/
    echo Pri ustanovke otmetyte: Add Python to PATH
    pause
    exit /b 1
)
python --version
echo OK: Python naiden
echo.

echo [2/4] Obnovlenie pip...
python -m pip install --upgrade pip --quiet
echo OK
echo.

echo [3/4] Ustanovka bibliotek...
echo Podozhdite 3-7 minut...
python -m pip install -r requirements.txt
echo.

echo [4/4] Proverka bibliotek...
python -c "import telegram; print('  OK: python-telegram-bot')" 2>nul
if errorlevel 1 (
    echo OSHIBKA: python-telegram-bot!
    pause
    exit /b 1
)
python -c "import anthropic; print('  OK: anthropic')" 2>nul
if errorlevel 1 (
    echo OSHIBKA: anthropic!
    pause
    exit /b 1
)
python -c "import aiohttp; print('  OK: aiohttp')" 2>nul
if errorlevel 1 (
    echo OSHIBKA: aiohttp!
    pause
    exit /b 1
)
python -c "import flask; print('  OK: flask')" 2>nul
if errorlevel 1 (
    echo OSHIBKA: flask!
    pause
    exit /b 1
)
python -c "import PIL; print('  OK: Pillow')" 2>nul
if errorlevel 1 (
    echo OSHIBKA: Pillow!
    pause
    exit /b 1
)
python -c "import aiofiles; print('  OK: aiofiles')" 2>nul
python -c "import pytesseract; print('  OK: pytesseract')" 2>nul
cd .

echo.

echo [Papki] Sozdanie papok...
if not exist knowledge_base mkdir knowledge_base
if not exist files_cache mkdir files_cache
echo   OK: knowledge_base, files_cache
echo.

if not exist config.py (
    if exist config.example.py (
        copy config.example.py config.py >nul
        echo   VNIMANIE: Sozdan config.py iz shablona!
        echo   ZAPOLNITE TOKENY v config.py pered zapuskom!
    )
) else (
    echo   OK: config.py naiden
)

echo. > .deps_installed

echo.
echo ============================================================
echo   Ustanovka zavershena!
echo   Zapustite start.bat dlya zapuska bota
echo ============================================================
echo.
pause
