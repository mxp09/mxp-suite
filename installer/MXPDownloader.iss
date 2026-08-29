; ============================================================================
;  MXP Downloader — Instalador
;
;  Instalador "online": pesa poco y descarga las dependencias durante la
;  instalación, verificándolas antes de dejar terminar. Ese es justo el
;  problema que resuelve: hasta ahora la app se repartía como un .zip y la
;  gente acababa con una copia instalada a la que le faltaba ffmpeg o el motor
;  de descarga, sin ninguna forma de saberlo hasta que algo fallaba.
;
;  Compilar:  iscc /DAppVersion=3.1.0 installer\MXPDownloader.iss
;  (normalmente lo lanza scripts\release.ps1, que saca la versión de
;   mxp_common\version.py para que no haya dos números que puedan divergir)
; ============================================================================

#ifndef AppVersion
  #define AppVersion "3.1.0"
#endif

#define AppName        "MXP Downloader"
#define AppPublisher   "MXP Productions"
#define AppExeName     "MXP Downloader.exe"
#define AppId          "{{8F2A6C41-3D7E-4B92-A5C8-1E9D4F7B2A63}"

; FFmpeg tiene una URL fija de "ultima version", asi que lo descarga el
; instalador. yt-dlp no: PyPI versiona cada wheel con su numero, asi que la
; URL hay que resolverla por API. De eso se encarga la propia app en el paso
; de verificacion, que ya sabe hacerlo.
#define FFmpegUrl  "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

[Setup]
; El AppId NO debe cambiar nunca entre versiones: es lo que hace que una
; actualización se instale encima en lugar de dejar dos copias.
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; Instalación por usuario: sin UAC, sin pedir contraseña de administrador.
; Un amigo al que le pasas un .exe no debería tener que ser admin para usarlo.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

OutputDir=..\dist\installer
OutputBaseFilename=MXP_Downloader_Setup_v{#AppVersion}
SetupIconFile=..\assets\logo_transparente.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\MXP Downloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Se borra lo que instalamos nosotros. El historial de descargas y los ajustes
; del usuario, que viven en %APPDATA%\MXP_Downloader, se respetan a propósito:
; desinstalar para reinstalar no debería perder los datos de nadie.
Type: filesandordirs; Name: "{app}"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  DepsPage: TOutputProgressWizardPage;
  FFmpegZipPath: String;
  DepsInstalled: Boolean;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if ProgressMax <> 0 then
    Log(Format('Descargados %d de %d bytes', [Progress, ProgressMax]));
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(
    'Descargando componentes necesarios',
    'La aplicación necesita FFmpeg y el motor de descarga para funcionar.',
    @OnDownloadProgress);

  DepsPage := CreateOutputProgressPage(
    'Instalando componentes',
    'Comprobando que todo funcione correctamente...');

  DepsInstalled := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  // Las dependencias se descargan justo antes de instalar los archivos, para
  // no hacer esperar al usuario si va a cancelar en la pantalla anterior.
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#FFmpegUrl}', 'ffmpeg.zip', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        FFmpegZipPath := ExpandConstant('{tmp}\ffmpeg.zip');
      except
        // Que falle la descarga aquí no es fatal: la app sabe reintentarla
        // ella sola al arrancar. Se avisa y se deja continuar.
        FFmpegZipPath := '';
        if MsgBox('No se pudieron descargar los componentes.' + #13#10#13#10 +
                  'Puedes continuar con la instalación: la aplicación volverá a ' +
                  'intentarlo la primera vez que la abras.' + #13#10#13#10 +
                  '¿Continuar de todos modos?',
                  mbConfirmation, MB_YESNO) = IDNO then
          Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  // Ya con los archivos copiados, se le pide a la propia app que instale y
  // VERIFIQUE las dependencias. Se reutiliza su código en vez de reimplementar
  // la extracción aquí, de modo que la comprobación —ejecutar el binario y ver
  // que responde— es exactamente la misma que hace la app en cada arranque.
  if CurStep = ssPostInstall then
  begin
    DepsPage.SetText('Instalando y verificando FFmpeg y el motor de descarga...', '');
    DepsPage.SetProgress(0, 100);
    DepsPage.Show;
    try
      Params := '--setup-deps';
      if FFmpegZipPath <> '' then
        Params := Params + ' --ffmpeg-zip "' + FFmpegZipPath + '"';

      DepsPage.SetProgress(30, 100);
      if Exec(ExpandConstant('{app}\{#AppExeName}'), Params, '',
              SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        DepsInstalled := (ResultCode = 0)
      else
        DepsInstalled := False;

      DepsPage.SetProgress(100, 100);
    finally
      DepsPage.Hide;
    end;

    if not DepsInstalled then
      MsgBox('La instalación ha terminado, pero algunos componentes no se ' +
             'pudieron preparar.' + #13#10#13#10 +
             'La aplicación volverá a intentarlo automáticamente al abrirse. ' +
             'Asegúrate de tener conexión a internet la primera vez que la uses.',
             mbInformation, MB_OK);
  end;
end;
