<#
  Se ejecuta DENTRO de Windows Sandbox (un Windows limpio que nunca tuvo nada).
  Instala MXP Suite en silencio, ejecuta la autoprueba y deja los resultados en
  la carpeta compartida "out". Al terminar apaga el Sandbox.

  Escenarios:
    clean    Windows limpio con internet: todo, incluidas descargas y transcripción.
    offline  Sin red: la instalación debe funcionar igual; solo falla lo que necesita red.
    accents  Instalación y descargas en carpetas con acentos, ñ y espacios.
    upgrade  Primero la 3.2.1 (Python) con datos del usuario y encima la 4.0.
#>
param([Parameter(Mandatory)] [string]$Scenario)

$ErrorActionPreference = "Continue"
$Desk = "C:\Users\WDAGUtilityAccount\Desktop"
$Out = "$Desk\out"
$Inst = "$Desk\installer"
New-Item -ItemType Directory -Force $Out | Out-Null
Start-Transcript "$Out\transcript.txt" | Out-Null

function Note($k, $v) { "$k = $v" | Tee-Object -FilePath "$Out\summary.txt" -Append }

Note "escenario" $Scenario
Note "windows" ((Get-CimInstance Win32_OperatingSystem).Caption + " " + [Environment]::OSVersion.Version)
# Lo que un PC "de fábrica" no trae y la 3.x daba por hecho:
Note "vcruntime140 en System32" (Test-Path "$env:SystemRoot\System32\vcruntime140.dll")
Note "vcomp140 en System32" (Test-Path "$env:SystemRoot\System32\vcomp140.dll")
Note "python en PATH" ([bool](Get-Command python -ErrorAction SilentlyContinue))

$setup = Get-ChildItem "$Inst\MXP_Downloader_Setup_v4*.exe" | Select-Object -First 1
$args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOMODELS", "/LOG=`"$Out\install.log`"")

if ($Scenario -eq "upgrade") {
    # La 3.2.1 real, con un historial y ajustes de usuario que deben sobrevivir.
    $old = Get-ChildItem "$Inst\legacy\MXP_Downloader_Setup_v3*.exe" | Select-Object -First 1
    $p = Start-Process $old.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$Out\install-3x.log`"" -Wait -PassThru
    Note "instalación 3.x (código)" $p.ExitCode
    $data = "$env:APPDATA\MXP_Downloader"
    New-Item -ItemType Directory -Force $data | Out-Null
    '[{"title":"Video de antes","url":"https://youtu.be/x","format":"MP4","date":"2026-10-01 10:00:00"}]' | Set-Content "$data\history.json" -Encoding UTF8
    '{"output_dir":"C:/Users/WDAGUtilityAccount/Videos","mode":"audio_only","audio_format":"FLAC"}' | Set-Content "$data\settings.json" -Encoding UTF8
}
if ($Scenario -eq "accents") {
    $dir = "$env:LOCALAPPDATA\Programs\Ñandú Programas\MXP Suite (prueba)"
    $args += "/DIR=`"$dir`""
}

$t0 = Get-Date
$p = Start-Process $setup.FullName -ArgumentList $args -Wait -PassThru
Note "instalación 4.0 (código, 0 = bien)" $p.ExitCode
Note "instalación 4.0 (segundos)" ([int]((Get-Date) - $t0).TotalSeconds)

$key = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F2A6C41-3D7E-4B92-A5C8-1E9D4F7B2A63}_is1" -ErrorAction SilentlyContinue
$app = $key.InstallLocation.TrimEnd('\')
Note "carpeta" $app
Note "versión registrada" $key.DisplayVersion
$exe = Join-Path $app "MXP Suite.exe"
Note "exe presente" (Test-Path $exe)

if ($Scenario -eq "upgrade") {
    Note "restos 3.x borrados (_internal)" (-not (Test-Path "$app\_internal"))
    Note "exe viejo borrado" (-not (Test-Path "$app\MXP Downloader.exe"))
    Note "historial conservado" ((Get-Content "$env:APPDATA\MXP_Downloader\history.json" -Raw) -match "Video de antes")
    Note "ajustes conservados" ((Get-Content "$env:APPDATA\MXP_Downloader\settings.json" -Raw) -match "FLAC")
}

if (Test-Path $exe) {
    # Autoprueba completa (descargas y transcripción reales). En "offline" se
    # espera que fallen solo las pruebas de red.
    $full = if ($Scenario -eq "offline") { @() } else { @("--full") }
    $t0 = Get-Date
    $p = Start-Process $exe -ArgumentList (@("--self-test") + $full + @("--report", "`"$Out\selftest.json`"")) -Wait -PassThru
    Note "autoprueba (código, 0 = bien)" $p.ExitCode
    Note "autoprueba (segundos)" ([int]((Get-Date) - $t0).TotalSeconds)

    # La ventana de verdad: tiene que abrir y seguir viva (WebView2, permisos…).
    $p = Start-Process $exe -PassThru
    Start-Sleep 12
    $p.Refresh()
    Note "ventana abierta tras 12 s" (-not $p.HasExited -and $p.MainWindowTitle -eq "MXP Suite")
    Note "RAM de la app (MB)" ([int]($p.WorkingSet64 / 1MB))
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    $b = [Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object Drawing.Bitmap $b.Width, $b.Height
    [Drawing.Graphics]::FromImage($bmp).CopyFromScreen(0, 0, 0, 0, $bmp.Size)
    $bmp.Save("$Out\pantalla.png")
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}

Copy-Item "$env:APPDATA\MXP_Downloader\logs" "$Out\logs" -Recurse -ErrorAction SilentlyContinue
Stop-Transcript | Out-Null
"fin" | Set-Content "$Out\done.txt"
Stop-Computer -Force
