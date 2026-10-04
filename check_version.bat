@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Version Check - AI_Diag_UZ

echo.
echo ============================================================
echo   CURRENT PROJECT VERSION
echo   Copy the HEAD line and paste it to Claude chat
echo ============================================================
echo.

git log --oneline -1 > temp_head.txt
set /p HEAD_LINE=<temp_head.txt
del temp_head.txt

echo   HEAD: %HEAD_LINE%
echo.
echo ============================================================
echo.
pause
