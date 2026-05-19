@echo off
REM ============================================================================
REM Groundwater Drawdown Tool - Installer / Updater
REM
REM Two modes, auto-detected:
REM
REM 1. BOOTSTRAP MODE - setup.bat is run from outside the install folder (e.g.
REM    Downloads). It downloads the latest release from GitHub, extracts it to
REM    %USERPROFILE%\Tools\groundwater-drawdown-tool, then chains into the
REM    extracted setup.bat to install Python dependencies. If the install folder
REM    already exists with an older version, the release files are refreshed in
REM    place; user data (.env, outputs\, logs\, flask_session\) is preserved.
REM
REM 2. LOCAL MODE - setup.bat is run from inside an installed (or cloned) copy
REM    of the tool. It installs uv if needed and runs `uv sync` to install or
REM    refresh Python dependencies. No network calls to GitHub.
REM
REM Daily use: double-click run.bat from the install folder.
REM ============================================================================

setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

REM --- Mode detection -------------------------------------------------------
REM A bootstrap copy of setup.bat sits alone (no pyproject.toml next to it).
REM A local copy lives inside the installed/cloned tree.
if exist "pyproject.toml" if exist "src\gwdrawdown\__init__.py" goto :local_mode
goto :bootstrap_mode


REM ============================================================================
REM LOCAL MODE - install / refresh dependencies for this copy of the tool
REM ============================================================================
:local_mode

echo.
echo ============================================================================
echo Groundwater Drawdown Tool - Dependency setup
echo ============================================================================
echo.

if exist "version.txt" (
    set /p TOOL_VERSION=<"version.txt"
    echo Tool version: !TOOL_VERSION!
    echo.
)

call :ensure_uv
if errorlevel 1 exit /b 1

echo.
echo Installing Python dependencies (uv sync)...
echo This may take a few minutes on first run.
echo.
uv sync
if errorlevel 1 (
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
echo To run the tool, double-click run.bat in this folder:
echo   %CD%\run.bat
echo You will be asked to sign in with your BCGW credentials in your browser.
echo ============================================================================
echo.
pause
exit /b 0


REM ============================================================================
REM BOOTSTRAP MODE - fetch the latest release from GitHub Releases
REM ============================================================================
:bootstrap_mode

set "REPO=bcgov/groundwater-drawdown-tool"
set "INSTALL_DIR=%USERPROFILE%\Tools\groundwater-drawdown-tool"
set "ZIP_URL=https://github.com/%REPO%/releases/latest/download/groundwater-drawdown-tool.zip"
set "API_URL=https://api.github.com/repos/%REPO%/releases/latest"

echo.
echo ============================================================================
echo Groundwater Drawdown Tool - Installer / Updater
echo ============================================================================
echo.
echo Install folder: %INSTALL_DIR%
echo.

REM --- Look up the latest published version --------------------------------
echo Checking GitHub for the latest release...
set "REMOTE_VERSION="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%API_URL%' -UseBasicParsing -ErrorAction Stop; $r.tag_name.TrimStart('v').Trim() } catch { 'ERROR' }"`) do set "REMOTE_VERSION=%%V"

if "!REMOTE_VERSION!"=="ERROR" goto :network_error
if "!REMOTE_VERSION!"=="" goto :network_error

echo Latest release: !REMOTE_VERSION!
echo.

REM --- Decide: fresh install vs update vs already-up-to-date ---------------
if exist "%INSTALL_DIR%\pyproject.toml" goto :existing_install
goto :fresh_install


:fresh_install
echo No existing install detected. Performing a fresh install.
echo.
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" 2>nul
    if errorlevel 1 (
        echo ERROR: Could not create install folder: %INSTALL_DIR%
        pause
        exit /b 1
    )
)
call :download_and_extract "%INSTALL_DIR%" "!REMOTE_VERSION!"
if errorlevel 1 exit /b 1
goto :chain_local_setup


:existing_install
set "LOCAL_VERSION="
if exist "%INSTALL_DIR%\version.txt" set /p LOCAL_VERSION=<"%INSTALL_DIR%\version.txt"
if "!LOCAL_VERSION!"=="" set "LOCAL_VERSION=unknown"

echo Found existing install: version !LOCAL_VERSION!

if /i "!LOCAL_VERSION!"=="!REMOTE_VERSION!" (
    echo.
    echo The tool is already up to date.
    echo.
    echo To launch the tool, double-click:
    echo   %INSTALL_DIR%\run.bat
    echo.
    echo To re-install dependencies ^(rarely needed^), run:
    echo   %INSTALL_DIR%\setup.bat
    echo.
    pause
    exit /b 0
)

echo Updating from !LOCAL_VERSION! to !REMOTE_VERSION!
echo Your data ^(.env, outputs\, logs\, flask_session\^) will be preserved.
echo.
call :download_and_extract "%INSTALL_DIR%" "!REMOTE_VERSION!"
if errorlevel 1 exit /b 1
goto :chain_local_setup


:chain_local_setup
echo.
echo Files installed to %INSTALL_DIR%.
echo Running dependency setup inside the install folder...
echo.
pushd "%INSTALL_DIR%"
call "%INSTALL_DIR%\setup.bat"
set "CHAIN_RC=%ERRORLEVEL%"
popd
exit /b %CHAIN_RC%


REM ============================================================================
REM Helpers
REM ============================================================================

:download_and_extract
REM Args: %1 = target directory, %2 = version label (informational only)
set "TARGET=%~1"
set "VERSION_LABEL=%~2"
set "TMP_ZIP=%TEMP%\groundwater-drawdown-tool-!VERSION_LABEL!.zip"

if exist "!TMP_ZIP!" del "!TMP_ZIP!" >nul 2>nul

echo Downloading release archive...
echo   from %ZIP_URL%
echo   to   !TMP_ZIP!
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '!TMP_ZIP!' -UseBasicParsing -ErrorAction Stop } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo.
    echo ERROR: Download failed. Check your internet connection.
    echo If your network blocks github.com, contact IT.
    echo.
    pause
    exit /b 1
)

echo Extracting release archive...
REM Expand-Archive with -Force overwrites files in TARGET but leaves files
REM that aren't in the zip alone -- which is how we preserve .env, outputs\,
REM logs\, flask_session\. The release zip contains tool files only.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -Path '!TMP_ZIP!' -DestinationPath '!TARGET!' -Force -ErrorAction Stop } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo.
    echo ERROR: Extraction failed.
    echo.
    pause
    exit /b 1
)

del "!TMP_ZIP!" >nul 2>nul
exit /b 0


:ensure_uv
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo uv already installed.
    exit /b 0
)

echo Installing uv...
powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install uv.
    echo Check your internet connection and proxy settings, then try again.
    echo.
    pause
    exit /b 1
)

REM uv installs to %USERPROFILE%\.local\bin. Add to the current session PATH
REM so the next command finds it; new shells pick it up automatically.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: uv installed but is not on PATH. Open a new terminal and re-run setup.bat.
    echo.
    pause
    exit /b 1
)
exit /b 0


:network_error
echo.
echo ERROR: Could not reach GitHub to check for the latest release.
echo Check your internet connection and try again.
echo.
echo If your network blocks api.github.com or github.com, contact IT.
echo.
pause
exit /b 1
