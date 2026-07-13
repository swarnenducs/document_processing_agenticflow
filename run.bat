@echo off
REM Start FastAPI + Gradio UI together (Windows CMD).
REM Prefers Python script (run_both.py) so it works without uv on PATH.
REM Usage:
REM   run.bat
REM   run.bat --api-only
REM   run.bat --ui-only

cd /d "%~dp0"

REM 1) Prefer `py -3` (Windows Python launcher), then `python`
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run_both.py %*
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
    python run_both.py %*
    exit /b %ERRORLEVEL%
)

REM 2) Fallback to uv if Python is missing
where uv >nul 2>nul
if not errorlevel 1 (
    uv run doc-app %*
    exit /b %ERRORLEVEL%
)

echo [ERROR] Neither Python nor uv found on PATH.
echo Install Python 3.11+ from https://www.python.org/downloads/
echo   then:  pip install -r requirements.txt
echo   then:  python run_both.py
echo Or install uv: https://docs.astral.sh/uv/getting-started/installation/
exit /b 1
