@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Session Check - AI_Diag_UZ

echo.
echo ============================================================
echo   AI_Diag_UZ - SESSION INFO FOR CLAUDE
echo   Copy everything between the lines and paste to Claude
echo ============================================================
echo.

echo --- PASTE TO CLAUDE: START ---
echo.

echo PROJECT: AI_Diag_UZ Bot (CarDiag UZ)
echo RULES: See attached RULES.md
echo.

echo GIT STATUS:
git log --oneline -3
echo.

echo LOCAL CHANGES:
git status --short
echo.

echo UNCOMMITTED:
git diff --name-only
git diff --cached --name-only
echo.

echo --- PASTE TO CLAUDE: END ---
echo.
echo ============================================================
echo   Also attach RULES.md to your message
echo ============================================================
pause
