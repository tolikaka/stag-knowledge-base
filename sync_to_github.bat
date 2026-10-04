@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Git Sync - AI_Diag_UZ

REM -- Show current HEAD at the very start ----------------------
echo.
echo ============================================================
echo   CURRENT VERSION (copy HEAD line and paste to Claude):
git log --oneline -1 > temp_head.txt
set /p HEAD_LINE=<temp_head.txt
del temp_head.txt
echo   HEAD: %HEAD_LINE%
echo ============================================================
echo.

REM -- Check git installed --------------------------------------
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git not installed.
    echo Download: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM -- Check repo initialized -----------------------------------
if not exist ".git" (
    echo Initializing git repository...
    git init
    git remote add origin https://github.com/tolikaka/stag-knowledge-base.git
    echo.
    echo IMPORTANT: Run this script again after creating the repo.
    pause
    exit /b 1
)

REM -- Show current status --------------------------------------
echo Current status:
git status --short
echo.

REM -- Check if there are changes -------------------------------
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
    goto :do_commit
) else (
    echo No changes to commit.
    goto :push_only
)

:do_commit
REM -- Build auto commit message --------------------------------
set DATETIME=%date:~6,4%-%date:~3,2%-%date:~0,2% %time:~0,5%
set VERSION=unknown
if exist VERSION (
    set /p VERSION=<VERSION
)

echo Changes to commit:
git diff --name-only
git diff --cached --name-only
echo.

set /p MSG=Commit message (or Enter for auto): 
if "%MSG%"=="" set MSG=v%VERSION%: update %DATETIME%

REM -- Stage files ----------------------------------------------
git add *.py *.bat *.txt *.md 2>nul
git add files_cache\file_catalog.json 2>nul
git add knowledge_base\knowledge_base.json 2>nul

REM -- Never commit secrets -------------------------------------
git reset HEAD config.py 2>nul
git reset HEAD bot_session.session 2>nul
git reset HEAD debug_session.session 2>nul
git reset HEAD *.log 2>nul

echo.
echo Committing: %MSG%
git commit -m "%MSG%"

:push_only
REM -- Pull first to avoid rejected push -------------------------
git pull origin main --rebase --autostash >nul 2>&1
REM -- Push to GitHub -------------------------------------------
echo.
echo Pushing to GitHub...
git push origin main 2>nul
if errorlevel 1 (
    git push -u origin main
)

REM -- Show result ----------------------------------------------
echo.
echo ============================================================
echo   UPDATED VERSION (copy HEAD line and paste to Claude):
git log --oneline -1 > temp_head.txt
set /p NEW_HEAD=<temp_head.txt
del temp_head.txt
echo   HEAD: %NEW_HEAD%
echo ============================================================
echo.
git log --oneline -5
echo.
echo   Done. Repository updated.
echo ============================================================
pause
