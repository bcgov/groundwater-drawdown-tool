@echo off
REM ============================================================================
REM Groundwater Drawdown Tool - Launch the Dash app
REM
REM Starts the local web server on http://localhost:8050 and opens your default
REM browser. Sign in with your BCGW credentials when the page loads.
REM Close this window (or press Ctrl+C) to stop the tool.
REM
REM Before launching, this checks GitHub for a newer release and updates the
REM install in place if one is available. The check is silent when there is
REM nothing to update. Pass `--no-update` to skip the check (for example on a
REM slow network or when you want to launch immediately).
REM ============================================================================

setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

REM --- Argument parsing ---------------------------------------------------
set "SKIP_UPDATE=0"
if /i "%~1"=="--no-update" set "SKIP_UPDATE=1"

REM --- Silent auto-update -------------------------------------------------
REM Delegates to setup.bat --silent-update, which is designed to be invisible
REM when there is nothing to do, and never to block this script on failure.
if "%SKIP_UPDATE%"=="0" (
    if exist "%~dp0setup.bat" call "%~dp0setup.bat" --silent-update
)

REM Ensure uv is on PATH (in case PATH wasn't refreshed since setup)
where uv >nul 2>nul
if %errorlevel% neq 0 (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: uv not found. Run setup.bat first.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo Groundwater Drawdown Tool
echo ============================================================================
echo.
echo Starting the local web server...
echo.
echo Once it says "Dash is running on http://...", open your browser to:
echo.
echo     http://localhost:8050
echo.
echo Sign in with your BCGW username and password when the page loads.
echo.
echo To stop the tool, close this window or press Ctrl+C.
echo ============================================================================
echo.

REM Open the browser only once the Dash server is actually responding.
REM Delegates to _wait_and_open.ps1 (TCP port-poll on 8050, then `cmd
REM /c start` for the URL). Earlier inline-PowerShell attempts kept
REM getting mangled by cmd's quote handling — a separate .ps1 file
REM avoids the escaping problem entirely. Runs in the background so
REM the foreground Python launch on the next line is not held up.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_wait_and_open.ps1"

uv run python -m gwdrawdown.app

REM If we get here, the app exited.
echo.
echo Tool stopped.
pause
endlocal
