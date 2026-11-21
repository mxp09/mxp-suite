; ============================================================================
;  MXP Suite 4 — Instalador
;
;  Instalador COMPLETO: lleva dentro la app y todas sus herramientas (FFmpeg,
;  yt-dlp, Deno, whisper.cpp con su runtime). No necesita internet salvo para
;  los modelos de transcripción que elijas y, solo si falta, WebView2.
;
;  Antes de terminar ejecuta la autoprueba de la app (--self-test). Si algo
;  esencial no funciona en este PC, dice exactamente qué y no deja la app
;  instalada a medias.
;
;  Compilar: lo lanza scripts\release.ps1 (que pasa /DAppVersion=...).
; ============================================================================

#ifndef AppVersion
  #define AppVersion "4.0.0"
#endif

#define AppName      "MXP Suite"
#define AppPublisher "MXP Productions"
#define AppExeName   "MXP Suite.exe"
; MISMO AppId que la 3.x: así la 4.0 se instala encima y la sustituye.
#define AppId        "{{8F2A6C41-3D7E-4B92-A5C8-1E9D4F7B2A63}"
#define HFBase       "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://mxpsuite.tech
VersionInfoVersion={#AppVersion}
; Por usuario, sin pedir administrador (y sin UAC).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\MXP Downloader
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
; Windows 10 1809 o posterior, solo 64 bits (Windows 11 ARM lo emula).
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Cierra la app si está abierta (actualizaciones) y la reabre al terminar.
CloseApplications=force
RestartApplications=no
OutputDir=..\dist\installer
OutputBaseFilename=MXP_Downloader_Setup_v{#AppVersion}
SetupIconFile=..\src-tauri\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
spanish.WinVersionTooLowError=MXP Suite necesita Windows 10 (versión 1809) o Windows 11, de 64 bits.

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Restos de la 3.x (Python empaquetado): ocupan ~200 MB y ya no se usan.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\MXP Downloader.exe"
Type: files; Name: "{userdesktop}\MXP Downloader.lnk"
Type: files; Name: "{userprograms}\MXP Downloader\MXP Downloader.lnk"
Type: files; Name: "{userprograms}\MXP Downloader\Desinstalar MXP Downloader.lnk"
Type: dirifempty; Name: "{userprograms}\MXP Downloader"

[Files]
Source: "..\dist\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\vendor\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall dontcopy

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "tech.mxpsuite.app"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "tech.mxpsuite.app"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent; Check: InstallSucceeded

[UninstallDelete]
; Lo nuestro se borra; el historial, los ajustes y los modelos (%APPDATA%)
; se respetan: desinstalar para reinstalar no debe perder datos de nadie.
Type: filesandordirs; Name: "{app}"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  ModelPage: TInputOptionWizardPage;
  ModelTotal: TNewStaticText;
  ModelFiles, ModelShas, ModelNames: array[0..6] of String;
  ModelSizes: array[0..6] of Int64;
  ModelAllLast, ModelChanging, InstallAborted: Boolean;
  Problems: String;

procedure SetModel(I: Integer; FileName, Sha, Name: String; Size: Int64);
begin
  ModelFiles[I] := FileName; ModelShas[I] := Sha; ModelNames[I] := Name; ModelSizes[I] := Size;
end;

function SizeText(Bytes: Int64): String;
begin
  if Bytes >= 1000000000 then Result := Format('%.1f GB', [Bytes / 1000000000.0])
  else Result := Format('%d MB', [Round(Bytes / 1000000.0)]);
end;

function ModelsDir: String;
begin
  Result := ExpandConstant('{userappdata}\MXP_Downloader\models');
end;

// Ya instalado (por ejemplo desde la 3.x) = está y con el tamaño exacto.
function ModelInstalled(I: Integer): Boolean;
var
  Size: Int64;
begin
  Result := FileSize64(ModelsDir + '\' + ModelFiles[I], Size) and (Size = ModelSizes[I]);
end;

function SelectedModelBytes: Int64;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to 6 do
    if ModelPage.Values[I + 1] and not ModelInstalled(I) then Result := Result + ModelSizes[I];
end;

procedure ModelsChanged(Sender: TObject);
var
  I: Integer;
  All: Boolean;
  Free, Total: Int64;
begin
  if ModelChanging then exit;
  ModelChanging := True;
  if ModelPage.Values[0] <> ModelAllLast then
    for I := 1 to 7 do ModelPage.Values[I] := ModelPage.Values[0]
  else begin
    All := True;
    for I := 1 to 7 do All := All and ModelPage.Values[I];
    ModelPage.Values[0] := All;
  end;
  ModelAllLast := ModelPage.Values[0];
  ModelChanging := False;
  ModelTotal.Caption := 'A descargar: ' + SizeText(SelectedModelBytes);
  if GetSpaceOnDisk64(ExpandConstant('{userappdata}'), Free, Total) then
    ModelTotal.Caption := ModelTotal.Caption + '   ·   Libre en disco: ' + SizeText(Free);
end;

function WebView2Installed: Boolean;
var
  V: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

procedure InitializeWizard;
var
  I: Integer;
begin
  DownloadPage := CreateDownloadPage('Descargando modelos de transcripción',
    'Puede tardar según los modelos elegidos y tu conexión.', nil);

  SetModel(0, 'ggml-tiny.bin', 'be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21', 'Tiny: pruebas, PCs muy lentos', 77691713);
  SetModel(1, 'ggml-base.bin', '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe', 'Base: rápido, voz clara', 147951465);
  SetModel(2, 'ggml-small.bin', '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b', 'Small: equilibrado', 487601967);
  SetModel(3, 'ggml-large-v3-turbo-q5_0.bin', '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2', 'Large-v3-turbo comprimido: RECOMENDADO', 574041195);
  SetModel(4, 'ggml-medium.bin', '6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208', 'Medium: alta precisión (PESADO)', 1533763059);
  SetModel(5, 'ggml-large-v3-turbo.bin', '1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69', 'Large-v3-turbo: máxima precisión (PESADO)', 1624555275);
  SetModel(6, 'ggml-large-v3.bin', '64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2', 'Large-v3: máxima precisión, el más lento (PESADO)', 3095033483);

  ModelPage := CreateInputOptionPage(wpSelectTasks, 'Modelos de transcripción',
    'Elige qué modelos descargar para pasar audio y video a texto.',
    'Opcional: si no marcas ninguno, todo lo demás funciona y podrás bajarlos luego desde la app ' +
    '(Transcribir > Gestionar modelos). Los que ya tengas no se vuelven a descargar.', False, False);
  ModelPage.Add('Todos los modelos (unos 7,5 GB)');
  for I := 0 to 6 do
  begin
    if ModelInstalled(I) then ModelPage.Add(ModelNames[I] + '   (ya instalado)')
    else ModelPage.Add(ModelNames[I] + '   (' + SizeText(ModelSizes[I]) + ')');
  end;
  // Recomendado marcado por defecto, salvo que ya esté.
  ModelPage.Values[4] := not ModelInstalled(3);
  ModelPage.CheckListBox.OnClickCheck := @ModelsChanged;
  ModelPage.CheckListBox.Height := ScaleY(176);
  ModelTotal := TNewStaticText.Create(ModelPage);
  ModelTotal.Parent := ModelPage.Surface;
  ModelTotal.Top := ModelPage.CheckListBox.Top + ModelPage.CheckListBox.Height + ScaleY(8);
  ModelTotal.Font.Style := [fsBold];
  ModelAllLast := False;
  ModelsChanged(nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
  Free, Total: Int64;
begin
  Result := True;
  if CurPageID = ModelPage.ID then
  begin
    if GetSpaceOnDisk64(ExpandConstant('{userappdata}'), Free, Total) and (Free < SelectedModelBytes + 500000000) then
    begin
      MsgBox('No hay espacio en disco para los modelos elegidos.' + #13#10 +
             'Necesitas ' + SizeText(SelectedModelBytes + 500000000) + ' y hay ' + SizeText(Free) + ' libres.', mbError, MB_OK);
      Result := False;
    end;
  end;

  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    for I := 0 to 6 do
      if ModelPage.Values[I + 1] and not ModelInstalled(I) then
        // Inno comprueba el SHA-256: un modelo corrupto o a medias no se instala.
        DownloadPage.Add('{#HFBase}' + ModelFiles[I], ModelFiles[I], ModelShas[I]);
    if SelectedModelBytes > 0 then
    begin
      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
        except
          // Los modelos son opcionales: sin red se instala igual y se bajan luego.
          MsgBox('No se pudieron descargar los modelos de transcripción:' + #13#10 + GetExceptionMessage + #13#10#13#10 +
                 'MXP Suite se instalará igualmente. Podrás descargarlos luego desde la app (Transcribir > Gestionar modelos).',
                 mbInformation, MB_OK);
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
  end;
end;

function ReadSummary(Path: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if not LoadStringsFromFile(Path, Lines) then
  begin
    Result := '- No se pudo comprobar la instalación (¿el antivirus bloqueó MXP Suite?)';
    exit;
  end;
  for I := 0 to GetArrayLength(Lines) - 1 do
    if (Trim(Lines[I]) <> '') and (Trim(Lines[I]) <> 'OK') then
      Result := Result + '- ' + Trim(Lines[I]) + #13#10;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I, Code: Integer;
  Summary: String;
  Ok: Boolean;
begin
  if CurStep = ssInstall then
  begin
    // WebView2: Windows 11 lo trae; si falta, se instala ahora (por usuario, sin admin).
    if not WebView2Installed then
    begin
      WizardForm.StatusLabel.Caption := 'Instalando Microsoft Edge WebView2...';
      ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
      Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code);
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    // Modelos descargados → %APPDATA%\MXP_Downloader\models (donde los busca la app).
    ForceDirectories(ModelsDir);
    for I := 0 to 6 do
      if FileExists(ExpandConstant('{tmp}\') + ModelFiles[I]) and not ModelInstalled(I) then
        if not RenameFile(ExpandConstant('{tmp}\') + ModelFiles[I], ModelsDir + '\' + ModelFiles[I]) then
          CopyFile(ExpandConstant('{tmp}\') + ModelFiles[I], ModelsDir + '\' + ModelFiles[I], False);

    // Autoprueba real en ESTE PC antes de dar la instalación por buena.
    WizardForm.StatusLabel.Caption := 'Comprobando que todo funciona en este PC...';
    Summary := ExpandConstant('{tmp}\selftest.txt');
    repeat
      DeleteFile(Summary);
      Ok := Exec(ExpandConstant('{app}\{#AppExeName}'), '--self-test --summary "' + Summary + '"', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
      if Ok then Problems := '' else Problems := ReadSummary(Summary);
    until Ok or (MsgBox('Hay componentes que no funcionan en este PC:' + #13#10#13#10 + Problems + #13#10 +
                        'Si tienes antivirus, revisa si ha bloqueado algún archivo de MXP Suite.' + #13#10#13#10 +
                        '¿Reintentar?', mbError, MB_RETRYCANCEL) = IDCANCEL);
    if not Ok then
    begin
      // Sin lo esencial no se deja una app que luego falla: se deshace.
      InstallAborted := True;
      Exec(ExpandConstant('{uninstallexe}'), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewNoWait, Code);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and InstallAborted then
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'La instalación no se completó';
    WizardForm.FinishedLabel.Caption := 'MXP Suite no se instaló porque esto no funciona en este PC:' + #13#10#13#10 +
      Problems + #13#10 + 'Guarda este mensaje y escríbenos en mxpsuite.tech si no sabes resolverlo.';
  end;
end;

function InstallSucceeded: Boolean;
begin
  Result := not InstallAborted;
end;
