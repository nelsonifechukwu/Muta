$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-ExecutionPolicy Bypass -Scope Process -Force

if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}
$env:Path = "C:\ProgramData\chocolatey\bin;$env:Path"

choco install -y --no-progress `
    git python311 rustup.install cmake ninja nasm msys2 `
    visualstudio2022buildtools visualstudio2022-workload-vctools
if ($LASTEXITCODE -ne 0) { throw "Chocolatey dependency installation failed" }
$NodeVersion = "22.22.0"
$NodeHash = "b10f88c6ded24ca487839b3eccb8870a08d7f9fc2b9bb3b463fc72a3a40bcdb1"
$InstalledNode = if (Test-Path "C:\Program Files\nodejs\node.exe") {
    (& "C:\Program Files\nodejs\node.exe" --version).TrimStart("v")
} else { "" }
if ($InstalledNode -ne $NodeVersion) {
    choco uninstall -y --no-progress nodejs-lts
    $NodeMsi = Join-Path $env:TEMP "node-v$NodeVersion-x64.msi"
    Invoke-WebRequest "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-x64.msi" -OutFile $NodeMsi
    if ((Get-FileHash $NodeMsi -Algorithm SHA256).Hash.ToLowerInvariant() -ne $NodeHash) {
        throw "Pinned Node.js installer checksum mismatch"
    }
    $Msi = Start-Process msiexec.exe -ArgumentList "/i", $NodeMsi, "/qn", "/norestart" -Wait -PassThru
    if ($Msi.ExitCode -ne 0) { throw "Pinned Node.js installation failed: $($Msi.ExitCode)" }
}

$MsysRoot = if (Test-Path "C:\msys64") { "C:\msys64" } else { "C:\tools\msys64" }
$Bash = Join-Path $MsysRoot "usr\bin\bash.exe"
if (-not (Test-Path $Bash)) { throw "MSYS2 bash is missing" }
& $Bash -lc "pacman -Syu --noconfirm"
& $Bash -lc "pacman -S --needed --noconfirm git make diffutils file mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja mingw-w64-x86_64-nasm"
if ($LASTEXITCODE -ne 0) { throw "MSYS2 dependency installation failed" }

$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
$env:RUSTUP_NO_UPDATE_CHECK = "1"
$Rustup = Join-Path $env:USERPROFILE ".cargo\bin\rustup.exe"
& $Rustup toolchain install stable-x86_64-pc-windows-msvc --profile minimal
& $Rustup default stable-x86_64-pc-windows-msvc
New-Item -ItemType Directory -Force C:\MutaIncoming, C:\MutaPackageCache, C:\MutaPackageOutput | Out-Null
Write-Output "Windows package builder provisioned"
