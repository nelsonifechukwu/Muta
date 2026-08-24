param(
    [Parameter(Mandatory = $true)][string]$Root,
    [switch]$NestedOnly
)

$ErrorActionPreference = "Stop"
if (-not $env:WINDOWS_CERTIFICATE_BASE64 -or -not $env:WINDOWS_CERTIFICATE_PASSWORD) {
    throw "WINDOWS_CERTIFICATE_BASE64 and WINDOWS_CERTIFICATE_PASSWORD are required"
}

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Filter signtool.exe -Recurse |
    Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $signtool) {
    throw "64-bit signtool.exe was not found"
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ("muta-sign-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
$pfx = Join-Path $temporary "certificate.pfx"
try {
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_BASE64))
    if ($NestedOnly) {
        $roots = @((Join-Path $Root "gateway"), (Join-Path $Root "app-resources"))
        $files = foreach ($item in $roots) {
            if (Test-Path $item) {
                Get-ChildItem $item -Recurse -File |
                    Where-Object { $_.Extension -in ".exe", ".dll", ".pyd" }
            }
        }
    } else {
        $files = @()
        $main = Join-Path $Root "Muta.exe"
        if (Test-Path $main) { $files += Get-Item $main }
        $bundle = Join-Path $Root "bundle"
        if (Test-Path $bundle) {
            $files += Get-ChildItem $bundle -Recurse -File |
                Where-Object { $_.Extension -in ".exe", ".msi" }
        }
    }
    if (-not $files) { throw "no Windows files were found to sign below $Root" }
    foreach ($file in $files) {
        & $signtool.FullName sign /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 `
            /f $pfx /p $env:WINDOWS_CERTIFICATE_PASSWORD $file.FullName
        if ($LASTEXITCODE -ne 0) { throw "signtool failed for $($file.FullName)" }
        & $signtool.FullName verify /pa /all $file.FullName
        if ($LASTEXITCODE -ne 0) { throw "signature verification failed for $($file.FullName)" }
    }
} finally {
    Remove-Item -Recurse -Force $temporary -ErrorAction SilentlyContinue
}
