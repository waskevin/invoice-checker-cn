$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Compiler = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
$Script = Join-Path $ProjectRoot 'installer\InvoiceChecker.iss'

if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Inno Setup compiler not found.' }
& $Compiler $Script
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
