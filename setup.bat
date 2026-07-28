@echo off
REM ============================================================================
REM Groundwater Drawdown Tool - Installer / Updater
REM
REM Three modes, auto-detected or selected by argument:
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
REM 3. SILENT-UPDATE MODE - `setup.bat --silent-update` is called by run.bat
REM    before launching the app. It queries GitHub for the latest release, and
REM    if STRICTLY NEWER than the installed version, downloads and extracts it
REM    in place and refreshes dependencies. Silent when nothing has changed;
REM    never blocks the caller on failure. Logs to logs\auto-update.log.
REM    Skipped entirely in a git clone - developers update through git, and
REM    extracting a release zip over a working tree destroys uncommitted work.
REM
REM Daily use: double-click run.bat from the install folder.
REM ============================================================================

setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

REM --- Argument parsing -----------------------------------------------------
REM `--silent-update` is the auto-update entry point used by run.bat. It checks
REM GitHub for a newer release, updates in place if one is available, and exits.
REM It never pauses and never blocks the caller on failure.
set "SILENT_UPDATE=0"
if /i "%~1"=="--silent-update" set "SILENT_UPDATE=1"
if "%SILENT_UPDATE%"=="1" goto :silent_update_mode

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

REM Same forward-only rule as the silent path: only a genuinely newer remote
REM justifies overwriting the install. An unknown local version (missing or
REM empty version.txt) is the one case that still refreshes - the install is
REM already broken, this path is interactive, and user data is preserved.
set "REFRESH_INSTALL=0"
if /i "!LOCAL_VERSION!"=="unknown" (
    set "REFRESH_INSTALL=1"
) else (
    call :compare_versions "!LOCAL_VERSION!" "!REMOTE_VERSION!"
    if "!REMOTE_IS_NEWER!"=="1" set "REFRESH_INSTALL=1"
)

if "!REFRESH_INSTALL!"=="0" (
    echo.
    if /i "!LOCAL_VERSION!"=="!REMOTE_VERSION!" (
        echo The tool is already up to date.
    ) else (
        echo Your installed version ^(!LOCAL_VERSION!^) is newer than the latest
        echo published release ^(!REMOTE_VERSION!^). Leaving it untouched.
        echo.
        echo To go back to the published release, delete the install folder
        echo and run this installer again.
    )
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
echo Tool files copied to %INSTALL_DIR%.
echo.
echo NOT DONE YET - installing Python dependencies. This is the slow
echo step and can take a few minutes on first install. Please wait for
echo the "Setup complete" message before launching.
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


REM ============================================================================
REM :compare_versions <local> <remote>
REM
REM Sets REMOTE_IS_NEWER=1 only when <remote> is strictly newer than <local>,
REM and 0 otherwise - same version, older version, or anything that cannot be
REM parsed. VERSION_COMPARE_FAILED=1 flags the unparseable case so the caller
REM can log it; note that case still yields REMOTE_IS_NEWER=0, because
REM "we cannot tell" must never authorise overwriting an install.
REM
REM Comparison is delegated to PowerShell's [version] type so 0.5.10 sorts
REM after 0.5.9. A plain string compare gets that backwards.
REM ============================================================================
:compare_versions
set "REMOTE_IS_NEWER=0"
set "VERSION_COMPARE_FAILED=0"
set "_CMP_RESULT="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { if ([version]'%~2' -gt [version]'%~1') { 'NEWER' } else { 'NOT_NEWER' } } catch { 'UNPARSEABLE' }"`) do set "_CMP_RESULT=%%C"
if "!_CMP_RESULT!"=="NEWER" set "REMOTE_IS_NEWER=1"
if "!_CMP_RESULT!"=="UNPARSEABLE" set "VERSION_COMPARE_FAILED=1"
if "!_CMP_RESULT!"=="" set "VERSION_COMPARE_FAILED=1"
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


REM ============================================================================
REM SILENT UPDATE MODE - called by run.bat before launching the app
REM
REM Designed to be invisible when there is nothing to do, and to never block
REM the caller on failure. Reports briefly when an update is actually being
REM applied. Logs to logs\auto-update.log.
REM ============================================================================
:silent_update_mode

set "REPO=bcgov/groundwater-drawdown-tool"
set "API_URL=https://api.github.com/repos/%REPO%/releases/latest"
set "ZIP_URL=https://github.com/%REPO%/releases/latest/download/groundwater-drawdown-tool.zip"
set "INSTALL_DIR=%~dp0"
set "UPDATE_LOG=%INSTALL_DIR%logs\auto-update.log"

if not exist "%INSTALL_DIR%logs" mkdir "%INSTALL_DIR%logs" >nul 2>nul

REM --- Developer-clone guard ------------------------------------------------
REM A git clone updates through git, never through the release zip. Without
REM this guard, running run.bat inside a working tree extracts the published
REM release over the developer's source files and silently destroys any
REM uncommitted work. Note this is NOT about the version comparison below:
REM a perfectly legitimate upgrade would clobber the tree just the same.
REM Checked before the GitHub call so a clone makes no network request at all.
if exist "%INSTALL_DIR%.git" (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Developer clone detected ^(.git present^) - auto-update skipped.
    exit /b 0
)

set "LOCAL_VERSION="
if exist "%INSTALL_DIR%version.txt" set /p LOCAL_VERSION=<"%INSTALL_DIR%version.txt"

REM Query GitHub for the latest version. Any failure -> exit 0 (do not block).
set "REMOTE_VERSION="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%API_URL%' -UseBasicParsing -ErrorAction Stop; $r.tag_name.TrimStart('v').Trim() } catch { 'ERROR' }"`) do set "REMOTE_VERSION=%%V"

if "!REMOTE_VERSION!"=="ERROR" (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Could not reach GitHub to check for updates.
    exit /b 0
)
if "!REMOTE_VERSION!"=="" (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Empty response from GitHub releases API.
    exit /b 0
)

REM Only move FORWARD. An equality check alone is not enough: "different"
REM includes "older", so a local copy ahead of the published release would
REM download and extract the older one over itself and announce it as an
REM update. That bites in two real cases - a developer clone carrying an
REM unreleased version bump, and a release yanked or rolled back on GitHub,
REM which would silently downgrade every install on next launch.
call :compare_versions "!LOCAL_VERSION!" "!REMOTE_VERSION!"
if not "!REMOTE_IS_NEWER!"=="1" (
    if "!VERSION_COMPARE_FAILED!"=="1" (
        >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Could not compare versions ^(local '!LOCAL_VERSION!', remote '!REMOTE_VERSION!'^) - update skipped.
    )
    exit /b 0
)

REM Remote is genuinely newer - perform an in-place update.
echo.
echo An update is available: !LOCAL_VERSION! -^> !REMOTE_VERSION!
echo Downloading...

set "TMP_ZIP=%TEMP%\groundwater-drawdown-tool-!REMOTE_VERSION!.zip"
if exist "!TMP_ZIP!" del "!TMP_ZIP!" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '!TMP_ZIP!' -UseBasicParsing -ErrorAction Stop } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Download failed.
    echo Update download failed. Continuing with current version.
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -Path '!TMP_ZIP!' -DestinationPath '%INSTALL_DIR%' -Force -ErrorAction Stop } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] Extraction failed.
    echo Update extraction failed. Continuing with current version.
    del "!TMP_ZIP!" >nul 2>nul
    exit /b 0
)
del "!TMP_ZIP!" >nul 2>nul

echo Refreshing dependencies...

REM Defensive PATH prepend so uv is found even before any shell PATH refresh.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

uv sync
if errorlevel 1 (
    >> "%UPDATE_LOG%" echo [%DATE% %TIME%] uv sync failed after update.
    echo.
    echo Dependency refresh failed; you may need to re-run setup.bat manually.
    exit /b 0
)

echo Update complete: now on !REMOTE_VERSION!.
echo.
>> "%UPDATE_LOG%" echo [%DATE% %TIME%] Updated from !LOCAL_VERSION! to !REMOTE_VERSION!.
exit /b 0
