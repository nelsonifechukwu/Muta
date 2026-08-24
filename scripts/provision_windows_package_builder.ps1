$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-ExecutionPolicy Bypass -Scope Process -Force

if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}
$env:Path = "C:\ProgramData\chocolatey\bin;$env:Path"

choco install -y --no-progress `
    git python311 nodejs-lts rustup.install cmake ninja nasm msys2 `
    visualstudio2022buildtools visualstudio2022-workload-vctools
if ($LASTEXITCODE -ne 0) { throw "Chocolatey dependency installation failed" }

$Bash = "C:\msys64\usr\bin\bash.exe"
if (-not (Test-Path $Bash)) { throw "MSYS2 bash is missing" }
& $Bash -lc "pacman -Syu --noconfirm"
& $Bash -lc "pacman -S --needed --noconfirm git make diffutils file mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja mingw-w64-x86_64-nasm"
if ($LASTEXITCODE -ne 0) { throw "MSYS2 dependency installation failed" }

$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
rustup.exe toolchain install stable-x86_64-pc-windows-msvc --profile minimal
rustup.exe default stable-x86_64-pc-windows-msvc
New-Item -ItemType Directory -Force C:\MutaIncoming, C:\MutaPackageCache, C:\MutaPackageOutput | Out-Null
Write-Output "Windows package builder provisioned"
