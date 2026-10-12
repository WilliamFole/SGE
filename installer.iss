; ============================================================================
; SGE — Sistema de Gestão de Estoque
; Script do Inno Setup 6 para gerar o instalador Windows
; ============================================================================

#define MyAppName        "SGE"
#define MyAppFullName    "SGE — SERIES"
#define MyAppVersion     "1.2.0"
#define MyAppPublisher   "SGE"
#define MyAppURL         "http://localhost"
#define MyAppExeName     "SGE.exe"
#define MyInstallerName  "SGE_Setup_v" + MyAppVersion

[Setup]
AppId={{A1B2C3D4-E5F6-4789-ABCD-1234567890AB}
AppName={#MyAppFullName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppFullName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppFullName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

OutputDir=instalador
OutputBaseFilename={#MyInstallerName}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=6.1sp1
WizardStyle=modern

#if FileExists("static\img\app.ico")
SetupIconFile=static\img\favicon.ico
#endif

UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppFullName}

ShowLanguageDialog=auto

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "english";    MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ============================================================================
; FIX CRÍTICO: garante que utilizadores comuns podem escrever na pasta do app.
; Sem isto, o app falha ao criar dados\estoque.db em C:\Program Files.
; ============================================================================
[Dirs]
Name: "{app}";         Permissions: users-modify
Name: "{app}\dados";   Permissions: users-modify
Name: "{app}\backups"; Permissions: users-modify

[Files]
Source: "dist\SGE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#if FileExists("README.md")
Source: "README.md";   DestDir: "{app}"; Flags: ignoreversion isreadme
#endif
#if FileExists("LEIA-ME.txt")
Source: "LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\{#MyAppFullName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppFullName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppFullName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppFullName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version";     ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Code]
// ============================================================================
// Garante que as pastas dados/ e backups/ existem após a instalação
// ============================================================================
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not DirExists(ExpandConstant('{app}\dados')) then
      CreateDir(ExpandConstant('{app}\dados'));
    if not DirExists(ExpandConstant('{app}\backups')) then
      CreateDir(ExpandConstant('{app}\backups'));
  end;
end;