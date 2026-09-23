@echo off
setlocal
set "SOURCE=%~dp0"
set "TARGET=%LOCALAPPDATA%\InvoiceChecker"

echo Installing Invoice Checker...
robocopy "%SOURCE%" "%TARGET%" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS
if errorlevel 8 (
  echo Installation failed. Please close the application and try again.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\install-context-menu.ps1" -ExecutablePath "%TARGET%\InvoiceChecker-fixed\InvoiceChecker-fixed.exe"
if errorlevel 1 (
  echo The application was copied, but shortcut setup failed.
  pause
  exit /b 1
)

start "" "%TARGET%\InvoiceChecker-fixed\InvoiceChecker-fixed.exe"
echo Installation completed.
pause
