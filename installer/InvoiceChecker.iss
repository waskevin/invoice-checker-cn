#define AppName "Invoice Checker"
#define AppVersion "1.0.0"
#define AppExe "InvoiceChecker-fixed.exe"

[Setup]
AppId={{7B3E4D5D-398B-4C6E-A71E-BBE2A08108B7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Invoice Checker
DefaultDirName={localappdata}\Programs\InvoiceChecker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=InvoiceChecker-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\InvoiceChecker-fixed\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\InvoiceHotkey.exe"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Windows\SendTo\Invoice Checker"; Filename: "{app}\{#AppExe}"
Name: "{userstartup}\Invoice Checker Hotkey"; Filename: "{app}\{#AppExe}"; Parameters: "--hotkey-helper"

[Registry]
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: ""; ValueData: "Use Invoice Checker and copy total"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Use Invoice Checker and copy total"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\InvoiceCheckerBatch\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%*"""

Root: HKCU; Subkey: "Software\Classes\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: ""; ValueData: "Use Invoice Checker and copy total"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Use Invoice Checker and copy total"
Root: HKCU; Subkey: "Software\Classes\.pdf\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\.pdf\shell\InvoiceCheckerBatch\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%*"""

Root: HKCU; Subkey: "Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: ""; ValueData: "Use Invoice Checker and copy total"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Use Invoice Checker and copy total"
Root: HKCU; Subkey: "Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCU; Subkey: "Software\Classes\AllFilesystemObjects\shell\InvoiceCheckerBatch\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%*"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Invoice Checker"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Parameters: "--hotkey-helper"; Description: "Enable hotkey helper"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { The shortcut helper is now a hidden mode of the main executable. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM InvoiceChecker-fixed.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
