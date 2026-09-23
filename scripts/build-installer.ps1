param(
    [string]$AppVersion = ''
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CompilerCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$Script = Join-Path $ProjectRoot 'installer\InvoiceChecker.iss'

if (-not $Compiler) { throw 'Inno Setup compiler not found.' }
$Arguments = @()
if ($AppVersion) {
    $Arguments += "/DAppVersion=$AppVersion"
}
$Arguments += $Script
& $Compiler @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
