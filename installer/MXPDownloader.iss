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

; Motor de transcripcion (whisper.cpp) fijado con hash. Debe coincidir con
; WHISPER_ZIP_URL / WHISPER_ZIP_SHA256 en mxp_common\transcriber.py.
#define WhisperUrl "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip"
#define WhisperSha "49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a"
#define HFBase     "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

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
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent; Check: InstallSucceeded

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
  // Modelos de transcripcion (mismo catalogo que mxp_common\transcriber.py)
  ModelPage: TInputOptionWizardPage;
  ModelTotal: TNewStaticText;
  ModelKeys, ModelFiles, ModelShas, ModelNames: array[0..6] of String;
  ModelSizes: array[0..6] of Int64;
  ModelAllLast, ModelChanging: Boolean;
  WhisperZipPath: String;
  DepsProblems: String;   // lo que falta, para enseñarlo al usuario
  InstallAborted: Boolean;

procedure SetModel(I: Integer; Key, FileName, Sha, Name: String; Size: Int64);
begin
  ModelKeys[I] := Key; ModelFiles[I] := FileName; ModelShas[I] := Sha;
  ModelNames[I] := Name; ModelSizes[I] := Size;
end;

function SizeText(Bytes: Int64): String;
begin
  if Bytes >= 1000000000 then
    Result := Format('%.1f GB', [Bytes / 1000000000.0])
  else
    Result := Format('%d MB', [Round(Bytes / 1000000.0)]);
end;

function SelectedModelBytes: Int64;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to 6 do
    if ModelPage.Values[I + 1] then
      Result := Result + ModelSizes[I];
end;

procedure ModelsChanged(Sender: TObject);
var
  I: Integer;
  All: Boolean;
  Free, Total: Int64;
begin
  if ModelChanging then exit;
  ModelChanging := True;
  // Casilla "Todos": si cambio ella, arrastra al resto; si no, refleja al resto.
  if ModelPage.Values[0] <> ModelAllLast then
  begin
    for I := 1 to 7 do ModelPage.Values[I] := ModelPage.Values[0];
  end
  else
  begin
    All := True;
    for I := 1 to 7 do All := All and ModelPage.Values[I];
    ModelPage.Values[0] := All;
  end;
  ModelAllLast := ModelPage.Values[0];
  ModelChanging := False;

  ModelTotal.Caption := 'Total a descargar: ' + SizeText(SelectedModelBytes);
  if GetSpaceOnDisk64(ExpandConstant('{userappdata}'), Free, Total) then
    ModelTotal.Caption := ModelTotal.Caption + '   ·   Libre en disco: ' + SizeText(Free);
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if ProgressMax <> 0 then
    Log(Format('Descargados %d de %d bytes', [Progress, ProgressMax]));
  Result := True;
end;

procedure InitializeWizard;
var
  I: Integer;
begin
  DownloadPage := CreateDownloadPage(
    'Descargando componentes necesarios',
    'FFmpeg, el motor de descarga y la transcripción (puede tardar según los modelos elegidos).',
    @OnDownloadProgress);

  SetModel(0, 'tiny', 'ggml-tiny.bin', 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21', 'Tiny: pruebas, PCs muy lentos', 77691713);
  SetModel(1, 'base', 'ggml-base.bin', '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe', 'Base: rápido, voz clara', 147951465);
  SetModel(2, 'small', 'ggml-small.bin', '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b', 'Small: equilibrado', 487601967);
  SetModel(3, 'turbo-q5', 'ggml-large-v3-turbo-q5_0.bin', '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2', 'Large-v3-turbo comprimido: RECOMENDADO', 574041195);
  SetModel(4, 'medium', 'ggml-medium.bin', '6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208', 'Medium: alta precisión  (PESADO)', 1533763059);
  SetModel(5, 'turbo', 'ggml-large-v3-turbo.bin', '1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69', 'Large-v3-turbo: máxima precisión  (PESADO)', 1624555275);
  SetModel(6, 'large', 'ggml-large-v3.bin', '64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2', 'Large-v3: máxima precisión, el más lento  (PESADO)', 3095033483);

  ModelPage := CreateInputOptionPage(wpSelectTasks,
    'Modelos de transcripción',
    'Elige qué modelos descargar para transcribir audio y video a texto.',
    'Puedes marcar varios. Los marcados PESADO ocupan más de 1 GB y tardan en descargarse. ' +
    'Podrás añadir o borrar modelos después desde la app (Transcribir > Gestionar modelos).',
    False, False);
  ModelPage.Add('Todos los modelos (unos 7,5 GB: son modelos pesados, tardará según tu conexión)');
  for I := 0 to 6 do
    ModelPage.Add(ModelNames[I] + '   (' + SizeText(ModelSizes[I]) + ')');
  ModelPage.Values[4] := True;   // Large-v3-turbo comprimido por defecto
  ModelPage.CheckListBox.OnClickCheck := @ModelsChanged;
  ModelPage.CheckListBox.Height := ScaleY(176);   // deja sitio al total debajo
  ModelTotal := TNewStaticText.Create(ModelPage);
  ModelTotal.Parent := ModelPage.Surface;
  ModelTotal.Top := ModelPage.CheckListBox.Top + ModelPage.CheckListBox.Height + ScaleY(8);
  ModelTotal.Font.Style := [fsBold];
  ModelAllLast := False;
  ModelsChanged(nil);

  DepsPage := CreateOutputProgressPage(
    'Instalando componentes',
    'Comprobando que todo funcione correctamente...');

  DepsInstalled := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
  Free, Total: Int64;
  Done: Boolean;
begin
  Result := True;

  if CurPageID = ModelPage.ID then
  begin
    if SelectedModelBytes = 0 then
    begin
      MsgBox('Marca al menos un modelo para poder transcribir.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    // Margen de 500 MB sobre lo elegido para no dejar el disco a cero.
    if GetSpaceOnDisk64(ExpandConstant('{userappdata}'), Free, Total) and
       (Free < SelectedModelBytes + 500000000) then
    begin
      MsgBox('No hay espacio suficiente en disco para los modelos elegidos.' + #13#10 +
             'Necesitas ' + SizeText(SelectedModelBytes + 500000000) + ' y hay ' + SizeText(Free) + ' libres.',
             mbError, MB_OK);
      Result := False;
      exit;
    end;
  end;

  // Las dependencias se descargan justo antes de instalar los archivos, para
  // no hacer esperar al usuario si va a cancelar en la pantalla anterior.
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#FFmpegUrl}', 'ffmpeg.zip', '');
    // Inno verifica el SHA-256 de cada archivo que lo trae: un modelo
    // corrupto o a medias no llega a instalarse.
    DownloadPage.Add('{#WhisperUrl}', 'whisper.zip', '{#WhisperSha}');
    for I := 0 to 6 do
      if ModelPage.Values[I + 1] then
        DownloadPage.Add('{#HFBase}' + ModelFiles[I], ModelFiles[I], ModelShas[I]);
    DownloadPage.Show;
    try
      // No se sigue sin los componentes: si falla, se ofrece reintentar.
      repeat
        Done := True;
        try
          DownloadPage.Download;
        except
          Done := False;
          if MsgBox('No se pudieron descargar todos los componentes:' + #13#10 +
                    GetExceptionMessage + #13#10#13#10 +
                    'Comprueba tu conexión a internet. ¿Reintentar?',
                    mbError, MB_RETRYCANCEL) = IDCANCEL then
          begin
            Result := False;   // se queda en esta pantalla; no se instala a medias
            exit;
          end;
        end;
      until Done;
      FFmpegZipPath := ExpandConstant('{tmp}\ffmpeg.zip');
      WhisperZipPath := ExpandConstant('{tmp}\whisper.zip');
    finally
      DownloadPage.Hide;
    end;
  end;
end;

// Lee el resumen que deja --setup-deps: "OK" o una línea por componente que falta.
function ReadDepsResult(Path: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if not LoadStringsFromFile(Path, Lines) then
  begin
    Result := '- No se pudo comprobar la instalación (¿antivirus bloqueando la app?)';
    exit;
  end;
  for I := 0 to GetArrayLength(Lines) - 1 do
    if (Trim(Lines[I]) <> '') and (Trim(Lines[I]) <> 'OK') then
      Result := Result + '- ' + Trim(Lines[I]) + #13#10;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
  ResultCode: Integer;
  Params, ResultPath: String;
begin
  // Ya con los archivos copiados, se le pide a la propia app que instale y
  // VERIFIQUE las dependencias. Se reutiliza su código en vez de reimplementar
  // la extracción aquí, de modo que la comprobación —ejecutar el binario y ver
  // que responde— es exactamente la misma que hace la app en cada arranque.
  if CurStep = ssPostInstall then
  begin
    DepsPage.SetText('Instalando y verificando FFmpeg, el motor de descarga y la transcripción...', '');
    DepsPage.SetProgress(0, 100);
    DepsPage.Show;
    try
      ResultPath := ExpandConstant('{tmp}\deps_result.txt');
      Params := '--setup-deps --result-file "' + ResultPath + '"';
      if FFmpegZipPath <> '' then
        Params := Params + ' --ffmpeg-zip "' + FFmpegZipPath + '"';
      if WhisperZipPath <> '' then
        Params := Params + ' --whisper-zip "' + WhisperZipPath + '"';
      for I := 0 to 6 do
        if ModelPage.Values[I + 1] then
          Params := Params + ' --whisper-model "' + ModelKeys[I] + '=' +
                    ExpandConstant('{tmp}\') + ModelFiles[I] + '"';

      // No se termina "en verde" con dependencias a medias: si --setup-deps
      // falla (sin red, antivirus...), se ofrece reintentar en bucle. Cada
      // reintento descarga solo lo que falte; lo ya verificado se salta.
      repeat
        DepsPage.SetProgress(30, 100);
        DeleteFile(ResultPath);
        if Exec(ExpandConstant('{app}\{#AppExeName}'), Params, '',
                SW_HIDE, ewWaitUntilTerminated, ResultCode) then
          DepsInstalled := (ResultCode = 0)
        else
          DepsInstalled := False;
        if DepsInstalled then
          DepsProblems := ''
        else
          DepsProblems := ReadDepsResult(ResultPath);
        DepsPage.SetProgress(100, 100);
      until DepsInstalled or (MsgBox(
        'No se pudieron preparar estos componentes:' + #13#10#13#10 +
        DepsProblems + #13#10 +
        'Comprueba tu conexión a internet y que el antivirus no esté bloqueando la instalación.' + #13#10#13#10 +
        '¿Reintentar ahora?', mbError, MB_RETRYCANCEL) = IDCANCEL);
    finally
      DepsPage.Hide;
    end;

    // Sin todo lo necesario no se deja una app instalada que luego falla:
    // se deshace la instalación y se explica qué faltó.
    if not DepsInstalled then
    begin
      InstallAborted := True;
      Exec(ExpandConstant('{uninstallexe}'), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
           SW_HIDE, ewNoWait, ResultCode);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and InstallAborted then
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'La instalación no se completó';
    WizardForm.FinishedLabel.Caption :=
      'MXP Downloader no se instaló porque faltan componentes necesarios:' + #13#10#13#10 +
      DepsProblems + #13#10 +
      'Conéctate a internet y vuelve a ejecutar el instalador.';
  end;
end;

// [Run] solo ofrece "Abrir MXP Downloader" si la instalación quedó completa.
function InstallSucceeded: Boolean;
begin
  Result := not InstallAborted;
end;
