; ============================================================
; Script do Inno Setup — SGE · Sistema de Gestão de Estoque
; Gera: SGE.Setup.exe (instalador do aplicativo)
; ============================================================

#define MyAppName "SGE"
#define MyAppDisplayName "SGE — SERIES"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Folestechi industries, lda"
#define MyAppExeName "SGE.exe"
#define MyAppSetupName "SGE.Setup"

[Setup]
; NOTE: AppId único por aplicação — não altere depois do primeiro lançamento!
AppId={{SGE-2024-7C3E-4E6D-9B2A-1F8A3D4E5C67}
AppName={#MyAppName}
AppVerName={#MyAppDisplayName} v{#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments={#MyAppDisplayName}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppDisplayName}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=no

OutputDir=installer_output
OutputBaseFilename={#MyAppSetupName}

Compression=lzma2/ultra
SolidCompression=yes
InternalCompressLevel=ultra
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64 x64compatible

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ============================================================
; CORREÇÃO: remova ou comente as linhas abaixo se o ícone não for válido
; ============================================================
;SetupIconFile=static\img\iconsetup.ico
;UninstallDisplayIcon={app}\{#MyAppExeName}
;WizardSmallImageFile=static\img\iconsetup.ico
; ============================================================
; Em vez disso, o instalador usará o ícone padrão do Inno Setup.
; Se quiser usar um ícone personalizado, converta uma imagem para .ICO
; válido (com resoluções 16x16, 32x32, 48x48, 64x64, 128x128) e descomente
; as linhas acima, actualizando o caminho do ficheiro.
; ============================================================

AppMutex=SGE-APP-MUTEX-2024
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho no Ambiente de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "startupicon"; Description: "Executar automaticamente ao iniciar sessão"; GroupDescription: "Arranque:"; Flags: unchecked

[Dirs]
Name: "{app}"; Permissions: users-full
Name: "{app}\dados"; Permissions: users-full
Name: "{app}\static\img"; Permissions: users-full

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "dados\*"; DestDir: "{app}\dados"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\img\*"; DestDir: "{app}\static\img"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppDisplayName} agora"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Remove dados apenas se o utilizador confirmar (opcional). Os databases ficam por defeito.
; Type: filesandordirs; Name: "{app}\dados"

[UninstallRun]
; Garante que o SGE não fica em memória quando desinstalado.
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden shellexec skipifdoesntexist