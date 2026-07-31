; CIENTO IMMOBILIER Enterprise Desktop — Inno Setup Installer
; Compile with Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; IMPORTANT :
;   * Les raccourcis (Bureau, Menu Démarrer) pointent EXCLUSIVEMENT vers
;     CIENTO-IMMOBILIER.exe — jamais vers une URL HTTP.
;   * Le backend Flask est démarré en arrière-plan par l'exécutable,
;     l'utilisateur ne voit aucune adresse localhost.
;   * Toutes les icônes utilisent le logo officiel (assets/app.ico).

#define MyAppName "CIENTO IMMOBILIER"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ciento Immobilier"
#define MyAppURL "https://ciento-immobilier.com"
#define MyAppExeName "CIENTO-IMMOBILIER.exe"
#define MyAppAssocName "CIENTO IMMOBILIER Data File"
#define MyAppAssocExt ".ciento"

[Setup]
AppId={{B8F7A3D2-9C5E-4A1B-8D6F-2E3C7A9B0D1E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
AppUpdatesURL={#MyAppURL}/updates
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
PrivilegesRequired=admin
OutputDir=..\dist\installer
OutputBaseFilename=CientoImmobilier_Setup_{#MyAppVersion}
SetupIconFile=..\assets\installer.ico
WizardImageFile=..\assets\wizard_left.bmp
WizardSmallImageFile=..\assets\wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
AlwaysShowDirOnReadyPage=yes
DisableReadyPage=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
BeveledLabel={#MyAppName} {#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis:"; Flags: checkedonce
Name: "taskbaricon"; Description: "Épingler à la barre des tâches"; GroupDescription: "Raccourcis:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\app.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\installer.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\splash.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-desktop.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\backups"; Permissions: users-modify
Name: "{app}\exports"; Permissions: users-modify
Name: "{app}\temp"; Permissions: users-modify
Name: "{app}\app\static\uploads"; Permissions: users-modify
Name: "{app}\app\static\uploads\photos"; Permissions: users-modify
Name: "{app}\app\static\uploads\documents"; Permissions: users-modify

; Raccourcis — cible : l'exécutable Windows, jamais une URL.
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app.ico"; Comment: "{#MyAppName} Enterprise Desktop"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app.ico"; Comment: "{#MyAppName} Enterprise Desktop"; Tasks: desktopicon
Name: "{autoprograms}\{#MyAppName} (Désinstallation)"; Filename: "{uninstallexe}"; IconFilename: "{app}\assets\installer.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--shutdown"; Flags: runhidden waituntilterminated

[Code]
procedure PinToTaskbar(FileName: string);
var
  Shell, Folder, Item, Verbs, Verb: Variant;
  i: Integer;
begin
  try
    Shell := CreateOleObject('Shell.Application');
    Folder := Shell.Namespace(ExtractFilePath(FileName));
    Item := Folder.ParseName(ExtractFileName(FileName));
    Verbs := Item.Verbs;
    for i := 0 to Verbs.Count - 1 do
    begin
      Verb := Verbs.Item(i);
      if (Pos('pin', LowerCase(Verb.Name)) > 0) or
         (Pos('épingler', LowerCase(Verb.Name)) > 0) then
      begin
        Verb.DoIt;
        Break;
      end;
    end;
  except
    { L'épinglage peut être bloqué par les stratégies Windows : on ignore. }
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if CurStep = ssPostInstall then
    begin
        Log('Installation terminée avec succès');
        if WizardIsTaskSelected('taskbaricon') then
        begin
            PinToTaskbar(ExpandConstant('{app}\{#MyAppExeName}'));
        end;
    end;
end;

function InitializeUninstall: Boolean;
begin
    Result := True;
end;
