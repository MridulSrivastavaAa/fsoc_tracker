; installer.iss
; =============
; Inno Setup 6.3+ script for NETRA FSOC PAT Workstation
;
; Compile with:
;   ISCC.exe installer.iss
; or via build_release.bat

#define AppName    "NETRA - Next-Generation Emulation for Tracking & Real-Time Alignment"
#define AppVersion "1.0.0"
#define Publisher  "Team NavDrishti1"
#define AppURL     "https://github.com/MridulSrivastavaAa/fsoc_tracker"
#define AppExeName "NETRA.exe"

[Setup]
AppId={{8F3A6C52-1B7D-4E0A-9C41-5D2E7A90B613}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\NETRA
DefaultGroupName=NETRA
OutputDir=release
OutputBaseFilename=NETRA-Setup
SetupIconFile=assets\netra.ico
UninstallDisplayIcon={app}\NETRA.exe
WizardStyle=modern
WizardImageFile=assets\wizard_side.bmp
WizardSmallImageFile=assets\wizard_small.bmp
LicenseFile=LICENSE.txt
InfoBeforeFile=QUICKSTART.txt
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Components]
Name: "main";    Description: "NETRA Workstation Core (required)"; Types: full compact custom; Flags: fixed
Name: "plugins"; Description: "Algorithm Plugin Presets & SDK";    Types: full custom
Name: "samples"; Description: "Sample Scenarios & Benchmark Data"; Types: full custom

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Main application binaries bundled by PyInstaller
Source: "dist\NETRA\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; Components: main

; Optional Plugin presets
Source: "src\fsoc\plugins\*"; DestDir: "{app}\plugins_sdk"; Flags: recursesubdirs ignoreversion; Components: plugins

; Optional Sample configurations and test data
Source: "configs\*"; DestDir: "{app}\sample_configs"; Flags: recursesubdirs ignoreversion; Components: samples

; Documentation & legal
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: main
Source: "QUICKSTART.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: main

; VC++ redistributable (installed silently if present and missing on host)
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist; Check: NeedsVCRedist

[Icons]
Name: "{group}\NETRA";           Filename: "{app}\{#AppExeName}"
Name: "{group}\NETRA Quickstart"; Filename: "{app}\QUICKSTART.txt"
Name: "{group}\Uninstall NETRA"; Filename: "{uninstallexe}"
Name: "{autodesktop}\NETRA";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Run VC++ runtime installer silently only if needed
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ runtime..."; Check: NeedsVCRedist; Flags: skipifdoesntexist
; Post-installation launch option
Filename: "{app}\{#AppExeName}"; Description: "Launch NETRA now"; Flags: nowait postinstall skipifsilent

[Code]
// Check if 64-bit Visual C++ 2015-2022 redistributable is installed
function NeedsVCRedist: Boolean;
var
  Installed: Cardinal;
begin
  Result := True;
  // Check standard VC++ 2015-2022 x64 registry key
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
  begin
    if Installed = 1 then
      Result := False;
  end;
end;

// Note: Uninstall does NOT delete %APPDATA%\NETRA (preserves user reports, logs, and custom plugins)
