@echo off
REM Start FastAPI + Gradio UI together (Windows CMD).
REM Usage:
REM   run.bat
REM   run.bat --api-only
REM   run.bat --ui-only

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv is not installed or not on PATH.
    echo Install: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

uv run doc-app %*
exit /b %ERRORLEVEL%
