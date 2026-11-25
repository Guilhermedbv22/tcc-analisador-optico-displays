#ifndef IrisVersion
  #error IrisVersion is required
#endif

[Setup]
AppId={{41DC5910-A04E-4CE8-98D7-3EB5F0F48A2E}
AppName=Íris Desktop
AppVersion={#IrisVersion}
AppPublisher=Projeto Íris
AppPublisherURL=https://tcc-iris.netlify.app/
AppSupportURL=https://tcc-iris.netlify.app/projeto.html
AppUpdatesURL=https://tcc-iris.netlify.app/download.html
DefaultDirName={localappdata}\Programs\IrisDesktop
DefaultGroupName=Íris Desktop
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UninstallDisplayIcon={app}\IrisDesktop.exe
SetupIconFile=..\iris_desktop\assets\iris.ico
OutputDir=..\dist-windows
OutputBaseFilename=IrisDesktop-Setup-{#IrisVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#IrisVersion}.0

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked

[Files]
Source: "..\dist\IrisDesktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Íris Desktop"; Filename: "{app}\IrisDesktop.exe"
Name: "{userdesktop}\Íris Desktop"; Filename: "{app}\IrisDesktop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\IrisDesktop.exe"; Description: "Abrir o Íris Desktop"; Flags: nowait postinstall skipifsilent
