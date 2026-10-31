param(
    [switch]$SkipInstall,
    [switch]$SkipTests,
    [string]$GoogleClientConfig,
    [string]$DistPath = 'dist'
)

$ErrorActionPreference = 'Stop'
if ($GoogleClientConfig) {
    if (-not (Test-Path -LiteralPath $GoogleClientConfig -PathType Leaf)) {
        throw 'GoogleClientConfig must point to a Google Desktop OAuth client JSON file.'
    }
    $GoogleClientConfig = (Resolve-Path -LiteralPath $GoogleClientConfig).Path
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = if ([IO.Path]::IsPathRooted($DistPath)) {
    [IO.Path]::GetFullPath($DistPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $DistPath))
}
$workspacePrefix = [IO.Path]::GetFullPath($projectRoot) + [IO.Path]::DirectorySeparatorChar
if (-not $distRoot.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'DistPath must be a directory inside this project.'
}
$outputExecutable = Join-Path $distRoot 'UnifiedScheduler\UnifiedScheduler.exe'
foreach ($runningApp in (Get-Process -Name UnifiedScheduler -ErrorAction SilentlyContinue)) {
    if ($runningApp.Path -eq $outputExecutable) {
        throw 'This output copy of Unified Scheduler is running. Quit it from the tray, or use -DistPath dist\new-build.'
    }
}
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
& $pythonPath -c "import struct, sys; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The Windows build requires 64-bit Python on Windows.' }
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
$previousGoogleClientConfig = $env:UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG
try {
    if ($GoogleClientConfig) {
        $env:UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG = $GoogleClientConfig
    }
    & $pythonPath -m PyInstaller --clean --noconfirm --distpath $distRoot UnifiedScheduler.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
}
finally {
    if ($null -eq $previousGoogleClientConfig) {
        Remove-Item Env:\UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG -ErrorAction SilentlyContinue
    }
    else {
        $env:UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG = $previousGoogleClientConfig
    }
}
Write-Host "Built $outputExecutable. Distribute the entire UnifiedScheduler folder."
