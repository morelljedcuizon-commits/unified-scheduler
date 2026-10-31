param(
    [Parameter(Mandatory = $true)][string]$AppDirectory,
    [string]$OutputDirectory,
    [string]$IsccPath,
    [switch]$AllowLocalOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$appDirectoryPath = (Resolve-Path -LiteralPath $AppDirectory).Path
if (-not (Test-Path -LiteralPath $appDirectoryPath -PathType Container)) {
    throw 'AppDirectory must be a packaged application directory.'
}
if (-not $OutputDirectory) { $OutputDirectory = Split-Path -Parent $appDirectoryPath }
$outputDirectoryPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$sourcePrefix = $appDirectoryPath.TrimEnd('\') + '\'
if ($outputDirectoryPath.TrimEnd('\').Equals($appDirectoryPath.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase) -or
    $outputDirectoryPath.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The installer output must be outside the packaged application directory.'
}

if (-not $IsccPath) {
    $compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($compilerCommand) { $IsccPath = $compilerCommand.Source }
    else {
        $compilerCandidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $IsccPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
    throw 'Install Inno Setup 6.3 or newer from https://jrsoftware.org/isdl.php, or pass -IsccPath to ISCC.exe.'
}
$IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create the project Python environment before building an installer.'
}

& $pythonPath (Join-Path $PSScriptRoot 'check_release.py') $appDirectoryPath
if ($LASTEXITCODE -ne 0) { throw 'Distribution content check failed; no installer was prepared.' }
$manifest = Get-Content -LiteralPath (Join-Path $appDirectoryPath 'build-info.json') -Raw | ConvertFrom-Json
if ($manifest.application -ne 'Unified Scheduler') { throw 'Unexpected application in build-info.json.' }
$appVersion = [string]$manifest.version
if ($appVersion -notmatch '^\d+\.\d+\.\d+(\.\d+)?$' -or
    ($appVersion.Split('.') | Where-Object { [long]$_ -gt 65535 })) {
    throw 'Installer versions must have three or four numeric parts, each no greater than 65535.'
}
if (-not $manifest.google_client_included -and -not $AllowLocalOnly) {
    throw 'This package has no Google Desktop client. Use a Google-enabled release folder, or explicitly pass -AllowLocalOnly for a labeled local/Moodle installer.'
}
$baseName = if ($manifest.google_client_included) { 'UnifiedScheduler-Setup-windows-x64' } else { 'UnifiedScheduler-Setup-windows-x64-local-moodle' }
New-Item -ItemType Directory -Path $outputDirectoryPath -Force | Out-Null
$compilerArguments = @(
    "/DAppSource=$appDirectoryPath",
    "/DAppVersion=$appVersion",
    "/DInstallerOutput=$outputDirectoryPath",
    "/DInstallerBaseName=$baseName",
    (Join-Path $projectRoot 'installer\UnifiedScheduler.iss')
)
& $IsccPath @compilerArguments
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$installer = Join-Path $outputDirectoryPath ($baseName + '.exe')
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw 'The compiler did not produce the expected installer.' }
$digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath ($installer + '.sha256') -Value ($digest + '  ' + [IO.Path]::GetFileName($installer)) -Encoding ASCII
Write-Host "Prepared installer: $installer"
Write-Host 'The installer is unsigned. No GitHub Release was published.'
