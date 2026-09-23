param(
    [string]$ReleaseName = 'InvoiceChecker-Installer'
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourceApp = Join-Path $ProjectRoot 'dist\InvoiceChecker-fixed'
$OutputRoot = Join-Path $ProjectRoot 'release'
$Stage = Join-Path $OutputRoot $ReleaseName
$Zip = Join-Path $OutputRoot "$ReleaseName.zip"

if (-not (Test-Path -LiteralPath (Join-Path $SourceApp 'InvoiceChecker-fixed.exe'))) {
    throw 'Build the application before creating the installer package.'
}

Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
Copy-Item -LiteralPath $SourceApp -Destination (Join-Path $Stage 'InvoiceChecker-fixed') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-context-menu.ps1') -Destination $Stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall-context-menu.ps1') -Destination $Stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install_Invoice_Checker.cmd') -Destination $Stage
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall_Context_Menu.cmd') -Destination $Stage
Set-Content -LiteralPath (Join-Path $Stage 'README.txt') -Encoding utf8 -Value @'
Invoice Checker installation package

1. Extract this ZIP to a local folder.
2. Double-click Install_Invoice_Checker.cmd.
3. Use the desktop shortcut to open the application.
4. For batch PDF processing: right-click selected PDFs, Show more options,
   Send to, then choose the invoice-check command.

To remove only the context-menu shortcut, double-click Uninstall_Context_Menu.cmd.
'@
Compress-Archive -LiteralPath $Stage -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "Created: $Zip"
