@echo off
start /wait "" "%~dp0Muta-Setup.exe" /S
if not exist "%LOCALAPPDATA%\Muta\Muta.exe" (
  echo Muta installation was not found. 1>&2
  exit /b 1
)
"%LOCALAPPDATA%\Muta\Muta.exe" --install-model-pack "%~dp0model-pack"
