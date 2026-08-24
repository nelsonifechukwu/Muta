param(
    [Parameter(Mandatory = $true)][string]$SourceArchive,
    [string]$ModelArchive = "",
    [Parameter(Mandatory = $true)][string]$ModelKey,
    [Parameter(Mandatory = $true)][string]$Commit,
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$CacheRoot = "C:\MutaPackageCache",
    [string]$OutputRoot = "C:\MutaPackageOutput"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Commit -notmatch '^[0-9a-f]{40}$') { throw "Invalid commit SHA" }
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$') { throw "Invalid SemVer" }
if ($ModelKey -notmatch '^[0-9a-f]{64}$') { throw "Invalid model cache key" }

$SourceRoot = Join-Path $CacheRoot "source\$Commit"
$ModelRoot = Join-Path $CacheRoot "models\$ModelKey"
$Output = Join-Path $OutputRoot "$Commit\$Version"
if (Test-Path $SourceRoot) { Remove-Item -Recurse -Force $SourceRoot }
New-Item -ItemType Directory -Force $SourceRoot, $ModelRoot, $Output | Out-Null

& tar.exe -xf $SourceArchive -C $SourceRoot
if ($LASTEXITCODE -ne 0) { throw "Could not extract source archive" }

$ModelMarker = Join-Path $ModelRoot ".complete"
if (-not (Test-Path $ModelMarker)) {
    if (-not $ModelArchive -or -not (Test-Path $ModelArchive)) {
        throw "The persistent model cache is missing and no model archive was supplied"
    }
    & tar.exe -xf $ModelArchive -C $ModelRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not extract model archive" }
    New-Item -ItemType File -Force $ModelMarker | Out-Null
}
Copy-Item -Path (Join-Path $ModelRoot "*") -Destination $SourceRoot -Recurse -Force

$MsysRoot = if (Test-Path "C:\msys64") { "C:\msys64" } else { "C:\tools\msys64" }
$env:MSYSTEM = "MINGW64"
$env:CHERE_INVOKING = "1"
$env:MSYS2_PATH_TYPE = "inherit"
$env:Path = @(
    "C:\Program Files\nodejs",
    "C:\Program Files\CMake\bin",
    "C:\Program Files\NASM",
    (Join-Path $MsysRoot "mingw64\bin"),
    (Join-Path $MsysRoot "usr\bin"),
    "$env:USERPROFILE\.cargo\bin",
    $env:Path
) -join ";"

$env:MUTA_DESKTOP_HEARTBEAT_URL = "https://muta-fleet-ingest-3lobbxiywa-uc.a.run.app"
if (-not $env:MUTA_DESKTOP_HEARTBEAT_INGEST_KEY) {
    $Headers = @{ "Metadata-Flavor" = "Google" }
    $TokenReply = Invoke-RestMethod `
        -Headers $Headers `
        -Uri "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
    $SecretReply = Invoke-RestMethod `
        -Headers @{ Authorization = "Bearer $($TokenReply.access_token)" } `
        -Uri "https://secretmanager.googleapis.com/v1/projects/muta-adtc/secrets/muta-fleet-ingest-key/versions/latest:access"
    $env:MUTA_DESKTOP_HEARTBEAT_INGEST_KEY = [Text.Encoding]::UTF8.GetString(
        [Convert]::FromBase64String($SecretReply.payload.data)
    ).Trim()
}
if (-not $env:MUTA_DESKTOP_HEARTBEAT_INGEST_KEY) {
    throw "Fleet heartbeat ingest key is empty"
}

$Venv = Join-Path $CacheRoot "venvs\windows-x86_64"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    & py.exe -3.11 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python 3.11 environment" }
}
& $Python -m pip install --disable-pip-version-check -e "$SourceRoot[desktop]"
if ($LASTEXITCODE -ne 0) { throw "Could not install Python build dependencies" }

& $Python (Join-Path $SourceRoot "scripts\manual_desktop_worker.py") `
    --platform windows-x86_64 `
    --version $Version `
    --commit $Commit `
    --cache-root (Join-Path $CacheRoot "layers") `
    --output $Output
if ($LASTEXITCODE -ne 0) { throw "Windows desktop worker failed" }

Write-Output (Join-Path $Output "Muta_${Version}_windows-x86_64_offline.zip")
