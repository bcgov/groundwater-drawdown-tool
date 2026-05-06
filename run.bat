@echo off
REM ============================================================================
REM Groundwater Drawdown Tool - Launch the Dash app
REM
REM Starts the local web server on http://localhost:8050 and opens your default
REM browser. Sign in with your BCGW credentials when the page loads.
REM Close this window (or press Ctrl+C) to stop the tool.
REM ============================================================================

setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

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

REM Open browser after a short delay (background)
start "" /b cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8050"

uv run python -m gwdrawdown.app

REM If we get here, the app exited.
echo.
echo Tool stopped.
pause
endlocal
