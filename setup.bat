@echo off
REM ============================================================================
REM Groundwater Drawdown Tool - First-time setup
REM
REM Installs uv (if missing), downloads Python 3.13 via uv, creates a virtual
REM environment, and installs all dependencies from pyproject.toml / uv.lock.
REM
REM Run this once per machine. After setup completes, use run.bat for daily use.
REM No credentials needed here -- you sign in to BCGW each time you launch
REM the tool from the browser.
REM ============================================================================

setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ============================================================================
echo Groundwater Drawdown Tool - Setup
echo ============================================================================
echo.

REM --- Step 1: ensure uv is installed ---------------------------------------
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [1/2] uv not found. Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if !errorlevel! neq 0 (
        echo.
        echo ERROR: Failed to install uv.
        echo Check your internet connection and proxy settings, then try again.
        echo.
        pause
        exit /b 1
    )
    REM uv installs to %USERPROFILE%\.local\bin which is added to PATH for new
    REM sessions. Add it to the current session so the next commands work.
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
) else (
    echo [1/2] uv already installed. Skipping.
)

REM --- Step 2: sync project (downloads Python 3.13 + installs deps) ---------
echo.
echo [2/2] Setting up Python environment and installing dependencies...
echo This may take a few minutes on first run.
echo.

uv sync
if %errorlevel% neq 0 (
    echo.
    echo ERROR: uv sync failed.
    echo Check your internet connection. If your network blocks PyPI, contact IT.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo Setup complete.
echo.
echo To run the tool, double-click run.bat
echo You will be asked to sign in with your BCGW credentials in your browser.
echo ============================================================================
echo.
pause
endlocal
