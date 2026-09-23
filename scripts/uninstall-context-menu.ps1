$VerbPaths = @(
    "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\*\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\.pdf\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch"
)
foreach ($PdfAssociationPath in @("HKCU:\Software\Classes\.pdf", "HKLM:\Software\Classes\.pdf")) {
    if (Test-Path -LiteralPath $PdfAssociationPath) {
        $PdfProgId = (Get-Item -LiteralPath $PdfAssociationPath).GetValue("")
        if ($PdfProgId) { $VerbPaths += "HKCU:\Software\Classes\$PdfProgId\shell\InvoiceCheckerBatch" }
    }
}
foreach ($VerbPath in $VerbPaths | Select-Object -Unique) {
    if (Test-Path -LiteralPath $VerbPath) { Remove-Item -LiteralPath $VerbPath -Recurse -Force }
}
$MenuText = -join ([char[]](0x4F7F, 0x7528, 0x53D1, 0x7968, 0x6838, 0x9A8C, 0x5E76, 0x590D, 0x5236, 0x5408, 0x8BA1))
$SendToShortcut = Join-Path $env:APPDATA "Microsoft\Windows\SendTo\$MenuText.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Invoice Checker.lnk'
Remove-Item -LiteralPath $SendToShortcut, $DesktopShortcut -Force -ErrorAction SilentlyContinue
Write-Host "Context-menu command removed."
