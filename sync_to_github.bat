@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Git Sync - AI_Diag_UZ

echo.
echo ============================================================
echo   Git Sync - AI_Diag_UZ Bot
echo ============================================================

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git not installed.
    echo Download: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Check if repo initialized
if not exist ".git" (
    echo Initializing git repository...
    git init
    git remote add origin https://github.com/tolikaka/stag-bot.git
    echo.
    echo IMPORTANT: Create repository stag-bot on GitHub first.
    echo Then run this script again.
    pause
    exit /b 1
)

REM Show current status
echo.
echo Current status:
git status --short
echo.

REM Check if there are changes
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
    goto :do_commit
) else (
    echo No changes to commit.
    goto :push_only
)

:do_commit
REM Auto commit message with date and version
set DATETIME=%date:~6,4%-%date:~3,2%-%date:~0,2% %time:~0,5%

REM Read version from VERSION file if exists
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

git add *.py *.bat *.txt *.md *.json 2>nul
git add files_cache\file_catalog.json 2>nul
git add knowledge_base\knowledge_base.json 2>nul

REM Do NOT add secrets
git reset HEAD config.py 2>nul
git reset HEAD bot_session.session 2>nul
git reset HEAD *.log 2>nul

echo.
echo Committing: %MSG%
git commit -m "%MSG%"

:push_only
echo.
echo Pushing to GitHub...
git push origin main 2>nul
if errorlevel 1 (
    git push -u origin main
)

echo.
git log --oneline -5
echo.
echo ============================================================
echo   Done. Repository updated.
echo ============================================================
pause
