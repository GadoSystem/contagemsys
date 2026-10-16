; Instalador do ContagemSys (Inno Setup 6). Gerado por packaging\build_windows.bat
; a partir de dist\ContagemSys. Instala na pasta do usuario (sem administrador),
; porque config.yaml, .env, data\ e eventos\ sao gravados ao lado do exe.

#define AppName "ContagemSys"
#define AppVersion "5.3.0"

[Setup]
AppId={{6E2B7C1A-5F3D-4B8E-9A21-C0A7D4E5F612}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Rebano
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ContagemSys-Setup
SetupIconFile=contagemsys.ico
UninstallDisplayIcon={app}\ContagemSys.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
; Configuracoes do usuario sao preservadas em atualizacoes.
Source: "..\dist\ContagemSys\config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "..\dist\ContagemSys\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "..\dist\ContagemSys\*"; DestDir: "{app}"; Excludes: "\config.yaml,\.env"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ContagemSys.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\ContagemSys.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ContagemSys.exe"; Description: "Abrir o ContagemSys"; Flags: nowait postinstall skipifsilent
