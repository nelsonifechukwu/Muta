$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$User = "muta-builder"
if (-not (Get-LocalUser -Name $User -ErrorAction SilentlyContinue)) {
    $Password = ConvertTo-SecureString (([guid]::NewGuid().ToString("N")) + "aA1!") -AsPlainText -Force
    New-LocalUser -Name $User -Password $Password -PasswordNeverExpires | Out-Null
}
Add-LocalGroupMember -Group "Administrators" -Member $User -ErrorAction SilentlyContinue

$SshCapability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($SshCapability.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $SshCapability.Name | Out-Null
}
New-Item -ItemType Directory -Force C:\ProgramData\ssh | Out-Null
$Key = Invoke-RestMethod -Headers @{"Metadata-Flavor" = "Google"} `
    -Uri "http://metadata.google.internal/computeMetadata/v1/instance/attributes/muta-builder-ssh-key"
Set-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value $Key -Encoding ascii
& icacls.exe C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r `
    /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null

New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
    -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -PropertyType String -Force | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd
New-Item -ItemType Directory -Force C:\MutaIncoming, C:\MutaPackageCache, C:\MutaPackageOutput | Out-Null
