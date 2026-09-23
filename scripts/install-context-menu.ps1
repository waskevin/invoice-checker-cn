param(
    [string]$ExecutablePath = (Join-Path (Split-Path -Parent $PSScriptRoot) "dist\InvoiceChecker-fixed\InvoiceChecker-fixed.exe")
)

$FullExecutablePath = (Resolve-Path -LiteralPath $ExecutablePath -ErrorAction Stop).Path
$MenuText = -join ([char[]](0x4F7F, 0x7528, 0x53D1, 0x7968, 0x6838, 0x9A8C, 0x5E76, 0x590D, 0x5236, 0x5408, 0x8BA1))
$VerbPaths = @(
    "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\*\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\.pdf\shell\InvoiceCheckerBatch",
    "HKCU:\Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch"
)
$PdfProgId = $null
foreach ($PdfAssociationPath in @("HKCU:\Software\Classes\.pdf", "HKLM:\Software\Classes\.pdf")) {
    if (Test-Path -LiteralPath $PdfAssociationPath) {
        $CandidateProgId = (Get-Item -LiteralPath $PdfAssociationPath).GetValue("")
        if ($CandidateProgId) { $PdfProgId = $CandidateProgId; break }
    }
}
if ($PdfProgId) {
    $VerbPaths += "HKCU:\Software\Classes\$PdfProgId\shell\InvoiceCheckerBatch"
}

foreach ($VerbPath in $VerbPaths) {
    # The registry provider can silently leave the default value empty for a
    # path containing the literal '*' key.  Write through the .NET registry
    # API so every Explorer variant receives a complete verb definition.
    $SubKeyPath = $VerbPath -replace '^HKCU:\\', '' -replace '\\', '\\'
    $VerbKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($SubKeyPath)
    $VerbKey.SetValue('', $MenuText, [Microsoft.Win32.RegistryValueKind]::String)
    $VerbKey.SetValue('MUIVerb', $MenuText, [Microsoft.Win32.RegistryValueKind]::String)
    $VerbKey.SetValue('MultiSelectModel', 'Player', [Microsoft.Win32.RegistryValueKind]::String)
    $VerbKey.SetValue('Icon', "$FullExecutablePath,0", [Microsoft.Win32.RegistryValueKind]::String)
    $CommandKey = $VerbKey.CreateSubKey('command')
    $CommandKey.SetValue('', ('"{0}" "%*"' -f $FullExecutablePath), [Microsoft.Win32.RegistryValueKind]::String)
    $CommandKey.Dispose()
    $VerbKey.Dispose()
}

# A reliable legacy-menu fallback.  It appears under "Send to" and receives
# all selected files in the same way as the normal context-menu command.
$SendToPath = Join-Path $env:APPDATA 'Microsoft\Windows\SendTo'
New-Item -ItemType Directory -Path $SendToPath -Force | Out-Null
$ShortcutPath = Join-Path $SendToPath "$MenuText.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $FullExecutablePath
# Explorer supplies the selected file paths to a SendTo shortcut itself.
$Shortcut.Arguments = ''
$Shortcut.WorkingDirectory = Split-Path -Parent $FullExecutablePath
$Shortcut.IconLocation = "$FullExecutablePath,0"
$Shortcut.Save()

$DesktopShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Invoice Checker.lnk'
$DesktopShortcut = $Shell.CreateShortcut($DesktopShortcutPath)
$DesktopShortcut.TargetPath = $FullExecutablePath
$DesktopShortcut.WorkingDirectory = Split-Path -Parent $FullExecutablePath
$DesktopShortcut.IconLocation = "$FullExecutablePath,0"
$DesktopShortcut.Save()

Start-Process -FilePath "$env:SystemRoot\System32\ie4uinit.exe" -ArgumentList "-show" -WindowStyle Hidden -Wait

Write-Host "Context-menu command and desktop shortcut installed."
