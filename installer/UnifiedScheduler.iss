; Compile through scripts/build-installer.ps1 after inspecting the packaged app.
#ifndef AppSource
  #error AppSource must point to a validated UnifiedScheduler distribution
#endif
#ifndef AppVersion
  #error AppVersion must be supplied from build-info.json
#endif
#ifndef InstallerOutput
  #error InstallerOutput must be supplied
#endif
#ifndef InstallerBaseName
  #error InstallerBaseName must be supplied
#endif

[Setup]
#ifdef InstallerTestBuild
AppId=UnifiedScheduler.InstallerSmokeTest
CreateUninstallRegKey=no
#else
AppId={{4AF4B886-0C08-4F60-902A-4B9B115853E8}
#endif
AppName=Unified Scheduler
AppVersion={#AppVersion}
AppPublisher=Unified Scheduler
AppPublisherURL=https://morelljedcuizon-commits.github.io/unified-scheduler/
AppSupportURL=https://morelljedcuizon-commits.github.io/unified-scheduler/
AppUpdatesURL=https://github.com/morelljedcuizon-commits/unified-scheduler/releases
DefaultDirName={localappdata}\Programs\UnifiedScheduler
DefaultGroupName=Unified Scheduler
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#InstallerOutput}
OutputBaseFilename={#InstallerBaseName}
SetupIconFile={#AppSource}\_internal\assets\unified_scheduler_simple.ico
UninstallDisplayIcon={app}\UnifiedScheduler.exe
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Unified Scheduler Installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; User data and Windows Credential Manager entries are deliberately untouched.

#ifndef InstallerTestBuild
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\Unified Scheduler"; Filename: "{app}\UnifiedScheduler.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Unified Scheduler"; Filename: "{app}\UnifiedScheduler.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\UnifiedScheduler.exe"; Description: "Open Unified Scheduler"; Flags: nowait postinstall skipifsilent
#endif

[InstallDelete]
; Refresh only installer-owned generated runtime files. This also removes an
; old OAuth client when explicitly installing a local/Moodle-only build.
Type: filesandordirs; Name: "{app}\_internal"; Check: IsManagedInstallation

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[UninstallDelete]
Type: files; Name: "{app}\.unified-scheduler-installer"

[Code]
function IsManagedInstallation: Boolean;
var
  Marker: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{app}\.unified-scheduler-installer'), Marker)
    and (Marker = 'UnifiedScheduler-Installer-v1');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}\_internal')) and not IsManagedInstallation then
    Result := 'The destination already contains an application that was not installed by this installer. Move that application folder or choose a different destination with /DIR before continuing. Your existing files have not been changed.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if not SaveStringToFile(ExpandConstant('{app}\.unified-scheduler-installer'),
        'UnifiedScheduler-Installer-v1', False) then
      RaiseException('Could not record the installation identity.');
end;
