param(
    [string]$GoogleClientConfig,
    [switch]$AllowLocalOnly,
    [switch]$SkipInstall,
    [switch]$BuildInstaller,
    [string]$IsccPath
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($GoogleClientConfig) {
    $GoogleClientConfig = (Resolve-Path -LiteralPath $GoogleClientConfig).Path
}
if ($IsccPath) { $IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path }
Set-Location -LiteralPath $projectRoot
$selectedClient = $GoogleClientConfig
if (-not $selectedClient) { $selectedClient = $env:UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG }
if (-not $selectedClient) { $selectedClient = Join-Path $projectRoot 'local-config\google-oauth-client.json' }
$hasGoogleClient = Test-Path -LiteralPath $selectedClient -PathType Leaf
if (-not $hasGoogleClient -and -not $AllowLocalOnly) {
    throw 'Supply a Desktop OAuth client for a Google-enabled candidate, or explicitly use -AllowLocalOnly.'
}
if ($BuildInstaller) {
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
        throw 'Building an installer requires Inno Setup 6.3 or newer. Install it from https://jrsoftware.org/isdl.php or pass -IsccPath to ISCC.exe.'
    }
    $IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path
}

# Each candidate gets a fresh output directory; never replace a running app or
# mix a previous build's private/development files into the release archive.
$buildId = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$relativeOutput = 'dist\candidate-' + $buildId
$buildParameters = @{ DistPath = $relativeOutput; SkipInstall = $SkipInstall }
if ($GoogleClientConfig) { $buildParameters.GoogleClientConfig = $GoogleClientConfig }
& (Join-Path $PSScriptRoot 'build.ps1') @buildParameters

$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$appDirectory = Join-Path $projectRoot ($relativeOutput + '\UnifiedScheduler')
$executable = Join-Path $appDirectory 'UnifiedScheduler.exe'
$previousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $smokeProcess = Start-Process -FilePath $executable -ArgumentList '--demo','--smoke-test' -WindowStyle Hidden -PassThru
    if (-not $smokeProcess.WaitForExit(60000)) {
        Stop-Process -Id $smokeProcess.Id
        throw 'Packaged startup check timed out; no release archive was prepared.'
    }
    $smokeProcess.Refresh()
    if ($smokeProcess.ExitCode -ne 0) { throw 'Packaged startup check failed; no release archive was prepared.' }
}
finally {
    if ($null -eq $previousQtPlatform) { Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
    else { $env:QT_QPA_PLATFORM = $previousQtPlatform }
}

Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination $appDirectory
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\DISTRIBUTION_README.txt') -Destination (Join-Path $appDirectory 'READ-ME.txt')
$appVersion = & $pythonPath -c "from importlib.metadata import version; print(version('unified-scheduler'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not read the application version.' }
$revision = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Could not read the source revision.' }
$dirty = [bool](git status --porcelain)
$manifest = [ordered]@{
    application = 'Unified Scheduler'
    version = $appVersion.Trim()
    source_commit = $revision.Trim()
    source_has_uncommitted_changes = $dirty
    built_utc = [DateTime]::UtcNow.ToString('o')
    google_client_included = [bool]$hasGoogleClient
    google_publishing_status = 'Not checked by the build; verify in Google Cloud Console.'
    code_signed = $false
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $appDirectory 'build-info.json') -Encoding UTF8

# Validate the actual artifact before archiving it. No source/local-config
# directory is copied, and only the normalized Desktop client is allowed.
& $pythonPath (Join-Path $PSScriptRoot 'check_release.py') $appDirectory
if ($LASTEXITCODE -ne 0) { throw 'Distribution content check failed.' }
$flavor = if ($hasGoogleClient) { 'google' } else { 'local-moodle' }
$archive = Join-Path $projectRoot ($relativeOutput + "\UnifiedScheduler-$($appVersion.Trim())-windows-x64-$flavor.zip")
Compress-Archive -LiteralPath $appDirectory -DestinationPath $archive
$digest = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath ($archive + '.sha256') -Value ($digest + '  ' + [IO.Path]::GetFileName($archive)) -Encoding ASCII
Write-Host "Prepared candidate: $archive"
if ($BuildInstaller) {
    & (Join-Path $PSScriptRoot 'build-installer.ps1') -AppDirectory $appDirectory -IsccPath $IsccPath -AllowLocalOnly:$AllowLocalOnly
}
Write-Host 'Review and test this candidate before manually publishing a GitHub Release. No release was published.'
