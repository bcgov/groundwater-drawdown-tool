<#
.SYNOPSIS
    Build and publish a new release of the Groundwater Drawdown Tool to GitHub Releases.

.DESCRIPTION
    Reads version.txt, verifies the working tree is clean and on main, runs
    pytest, builds a release zip (excluding dev cruft and large reference
    files), tags the commit, pushes the tag, and creates the GitHub release
    with the zip and setup.bat as downloadable assets.

    End users download `setup.bat` from the stable URL
    https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat
    which pulls the matching `groundwater-drawdown-tool.zip` from the same
    release.

.PREREQUISITES
    - GitHub CLI installed and authenticated:
        winget install GitHub.cli
        gh auth login
    - Working tree clean, on `main`, version.txt bumped, CHANGELOG.md updated.

.PARAMETER SkipTests
    Skip the pytest run. Discouraged; use only if tests are known-broken on
    something unrelated and you've manually verified the build.

.PARAMETER Draft
    Create the GitHub release as a draft. Useful for reviewing the
    release before it goes live.

    Note: published releases are always marked `--latest` (never a
    pre-release), so releases/latest/download/<asset> always resolves
    to the newest release — the canonical install URL the auto-updater
    uses. Without --latest, `gh release create` defaults to
    prerelease=true on a repository with no prior releases, which 404s
    the latest URL and breaks the auto-updater.

.EXAMPLE
    .\scripts\publish_release.ps1

.EXAMPLE
    .\scripts\publish_release.ps1 -Draft
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'

# Move to repo root regardless of where the script was launched from.
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# --- Preflight checks -----------------------------------------------------

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "GitHub CLI (gh) is not installed. Install via: winget install GitHub.cli"
}

if (-not (Test-Path 'version.txt')) {
    Fail "version.txt not found at repo root."
}

$version = (Get-Content 'version.txt' -Raw).Trim()
if (-not $version) { Fail "version.txt is empty." }
$tag = "v$version"

Write-Host ""
Write-Host "Publishing release $tag" -ForegroundColor Cyan
Write-Host ("=" * 70)

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') {
    Fail "Not on main branch (currently on '$branch'). Switch to main first."
}

$status = git status --porcelain
if ($status) {
    Write-Host "Working tree changes:"
    Write-Host $status
    Fail "Working tree is not clean. Commit or stash first."
}

$existingTag = git tag --list $tag
if ($existingTag) {
    Fail "Tag $tag already exists locally. Bump version.txt before publishing."
}

# Confirm tag doesn't exist on remote either.
git fetch --tags origin 2>$null | Out-Null
$remoteTag = git ls-remote --tags origin $tag
if ($remoteTag) {
    Fail "Tag $tag already exists on origin. Bump version.txt before publishing."
}

# --- Tests ----------------------------------------------------------------

if (-not $SkipTests) {
    Write-Host ""
    Write-Host "Running pytest..." -ForegroundColor Cyan
    uv run pytest
    if ($LASTEXITCODE -ne 0) { Fail "Tests failed. Fix before publishing." }
} else {
    Write-Warning "Skipping tests (-SkipTests)"
}

# --- Build release zip ----------------------------------------------------

$zipPath = Join-Path $env:TEMP "groundwater-drawdown-tool.zip"
$stagingDir = Join-Path $env:TEMP "gwdd-release-staging-$version"

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDir | Out-Null

Write-Host ""
Write-Host "Staging release files..." -ForegroundColor Cyan

# Top-level files and folders that ship in the release. This is an
# allow-list: anything not named here is excluded, including the docs/
# site sources and the developer-only specification documents in spec/
# (PROJECT_PLAN.md, DATA_REFERENCE.md, DESIGN_NOTES.md).
$includes = @(
    'src',
    'data',
    'pyproject.toml',
    'uv.lock',
    '.python-version',
    'setup.bat',
    'run.bat',
    '_wait_and_open.ps1',
    'version.txt',
    'CHANGELOG.md',
    'README.md',
    'CLIENT_INSTALL.md',
    # Apache 2.0 §4(a): recipients of the work must get a copy of the licence.
    'LICENSE'
)

# Selected files from references/ (the rest are client-confidential).
$referenceFiles = @(
    'references/excel_chart_layout.md'
)

foreach ($item in $includes) {
    if (-not (Test-Path $item)) {
        Write-Warning "  skip (not found): $item"
        continue
    }
    $dest = Join-Path $stagingDir $item
    if ((Get-Item $item).PSIsContainer) {
        Copy-Item -Path $item -Destination $dest -Recurse -Force
    } else {
        $destParent = Split-Path $dest -Parent
        if (-not (Test-Path $destParent)) { New-Item -ItemType Directory -Path $destParent -Force | Out-Null }
        Copy-Item -Path $item -Destination $dest -Force
    }
}

foreach ($item in $referenceFiles) {
    if (-not (Test-Path $item)) { continue }
    $dest = Join-Path $stagingDir $item
    $destParent = Split-Path $dest -Parent
    if (-not (Test-Path $destParent)) { New-Item -ItemType Directory -Path $destParent -Force | Out-Null }
    Copy-Item -Path $item -Destination $dest -Force
}

# Strip __pycache__ and *.pyc that may have been copied.
Get-ChildItem -Path $stagingDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $stagingDir -Recurse -File -Include '*.pyc','*.pyo' -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host "Compressing to $zipPath ..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $stagingDir '*') -DestinationPath $zipPath -Force
$zipSizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "  -> $zipPath  ($zipSizeMB MB)"

Remove-Item $stagingDir -Recurse -Force

# --- Tag and push ---------------------------------------------------------

Write-Host ""
Write-Host "Tagging commit and pushing..." -ForegroundColor Cyan
git tag $tag
if ($LASTEXITCODE -ne 0) { Fail "git tag failed." }
git push origin $tag
if ($LASTEXITCODE -ne 0) { Fail "git push of tag failed." }

# --- Extract release notes from CHANGELOG ---------------------------------

$notes = "Release $version"
if (Test-Path 'CHANGELOG.md') {
    $changelog = Get-Content 'CHANGELOG.md' -Raw
    $escaped = [regex]::Escape($version)
    $pattern = "(?ms)^## \[$escaped\][^\n]*\n(.*?)(?=^## \[|\z)"
    $match = [regex]::Match($changelog, $pattern)
    if ($match.Success) {
        $notes = $match.Groups[1].Value.Trim()
    } else {
        # Fall back to the [Unreleased] section if the versioned section
        # hasn't been cut yet (publisher forgot — warn but don't block).
        $unreleased = [regex]::Match($changelog, "(?ms)^## \[Unreleased\][^\n]*\n(.*?)(?=^## \[|\z)")
        if ($unreleased.Success) {
            Write-Warning "CHANGELOG.md has no [$version] section yet; using [Unreleased] block as release notes."
            $notes = $unreleased.Groups[1].Value.Trim()
        }
    }
}

$notesFile = Join-Path $env:TEMP "gwdd-release-notes-$version.md"
Set-Content -Path $notesFile -Value $notes -Encoding utf8

# --- Create the GitHub release -------------------------------------------

Write-Host ""
Write-Host "Creating GitHub release $tag..." -ForegroundColor Cyan

$ghArgs = @(
    'release', 'create', $tag,
    '--title', "v$version",
    '--notes-file', $notesFile,
    $zipPath,
    'setup.bat'
)
if ($Draft) { $ghArgs += '--draft' }
# Always mark the release as --latest so releases/latest/download/<asset>
# resolves to it (the canonical install URL the auto-updater uses).
# Without --latest, gh release create defaults to prerelease=true on the
# first release in a repo, which makes releases/latest 404 and breaks the
# auto-updater URL.
$ghArgs += '--latest'

& gh @ghArgs
$ghExit = $LASTEXITCODE
Remove-Item $notesFile -Force -ErrorAction SilentlyContinue

if ($ghExit -ne 0) { Fail "gh release create failed (exit $ghExit)." }

Write-Host ""
Write-Host "Release $tag published." -ForegroundColor Green
Write-Host "URL: https://github.com/bcgov/groundwater-drawdown-tool/releases/tag/$tag"
Write-Host ""
Write-Host "End users can install or update by running:" -ForegroundColor Cyan
Write-Host "  https://github.com/bcgov/groundwater-drawdown-tool/releases/latest/download/setup.bat"
Write-Host ""
