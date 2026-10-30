param(
    [switch]$SkipInstall,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
}
if (-not $SkipInstall) {
    & $pythonPath -m pip install --no-cache-dir -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
}
if (-not $SkipTests) {
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        & $pythonPath -m pytest
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed; the application was not packaged.' }
    }
    finally {
        if ($null -eq $previousQtPlatform) {
            Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        }
        else {
            $env:QT_QPA_PLATFORM = $previousQtPlatform
        }
    }
}
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot '.build-cache'
& $pythonPath -m PyInstaller --clean --noconfirm UnifiedScheduler.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
Write-Host 'Built dist\UnifiedScheduler\UnifiedScheduler.exe. Distribute the entire UnifiedScheduler folder.'
