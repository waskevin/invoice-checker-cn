param(
    [string]$Python = "C:\venvs\invoice-checker\Scripts\python.exe",
    [string]$Name = "InvoiceChecker-fixed"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonCommand = if (Test-Path -LiteralPath $Python) {
    (Resolve-Path -LiteralPath $Python).Path
} elseif (Get-Command $Python -ErrorAction SilentlyContinue) {
    $Python
} else {
    throw "Python was not found: $Python"
}

& $PythonCommand -m pip install pyinstaller
& $PythonCommand -m PyInstaller --noconfirm --clean --windowed --onedir --name $Name --paths "$ProjectRoot\src" --collect-binaries PySide6 --collect-binaries shiboken6 "$ProjectRoot\launcher.py"
if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}
$ObsoleteHelper = Join-Path $ProjectRoot "dist\$Name\InvoiceHotkey.exe"
Remove-Item -LiteralPath $ObsoleteHelper -Force -ErrorAction SilentlyContinue
$RuntimePath = Join-Path $ProjectRoot "dist\$Name\_internal"
Remove-Item -LiteralPath (Join-Path $RuntimePath "icuuc.dll"), (Join-Path $RuntimePath "icudt78.dll") -Force -ErrorAction SilentlyContinue
Write-Host "Created: $ProjectRoot\dist\$Name\$Name.exe"
