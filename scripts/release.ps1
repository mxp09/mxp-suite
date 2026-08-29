<#
.SYNOPSIS
    Compila, empaqueta y publica una version de MXP Downloader.

.DESCRIPTION
    Un solo comando desde el codigo hasta el release publicado. La version
    sale de mxp_common\version.py y se propaga a todo lo demas, para que no
    vuelva a haber seis numeros de version contradictorios repartidos entre
    etiquetas de la interfaz, nombres de zip y manifiestos.

    Pasos:
      1. Lee la version
      2. PyInstaller  -> dist\MXP Downloader\
      3. Inno Setup   -> dist\installer\MXP_Downloader_Setup_vX.Y.Z.exe
      4. SHA256SUMS.txt (lo verifica el updater antes de ejecutar nada)
      5. gh release create

.PARAMETER SkipPublish
    Compila el instalador pero no publica nada. Util para probar en local.

.PARAMETER Notes
    Notas del release. Es el texto que vera el usuario en el popup de
    actualizacion, asi que conviene escribirlo pensando en el.

.EXAMPLE
    .\scripts\release.ps1 -SkipPublish
    .\scripts\release.ps1 -Notes "Arreglado el error 403 al descargar de YouTube."
#>
[CmdletBinding()]
param(
    [switch]$SkipPublish,
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Interprete usado para compilar. Debe coincidir con requires-python en
# pyproject.toml. Python 3.10 quedo descartado: yt-dlp ya avisa que lo
# deprecara y dejara de arrancar en el sin previo aviso (ver EngineManager).
$PyVersion = "3.11"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

# ── 1. Version, desde la unica fuente que existe ────────────────────────────
Write-Step "Leyendo la version"
$Version = (py "-$PyVersion" -c "import sys; sys.path.insert(0, '.'); from mxp_common.version import __version__; print(__version__)").Trim()
if (-not $Version) { throw "No se pudo leer la version de mxp_common\version.py" }
Write-Host "    Version: $Version"

$Tag = "v$Version"
$InstallerName = "MXP_Downloader_Setup_v$Version.exe"
$InstallerPath = Join-Path $ProjectRoot "dist\installer\$InstallerName"

# ── 2. Ejecutable ───────────────────────────────────────────────────────────
Write-Step "Compilando con PyInstaller"
py "-$PyVersion" -m PyInstaller --noconfirm --clean "MXP Downloader.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }

$ExePath = Join-Path $ProjectRoot "dist\MXP Downloader\MXP Downloader.exe"
if (-not (Test-Path $ExePath)) { throw "No se genero el ejecutable en $ExePath" }

# Comprobacion basica de que el binario arranca: el modo --setup-deps se
# ejecuta sin abrir ventana y devuelve 0 si las dependencias quedan listas.
# Mejor detectar aqui un build roto que despues de publicarlo.
Write-Step "Comprobando que el ejecutable arranca"
& $ExePath --setup-deps | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "El ejecutable no dejo las dependencias listas (codigo $LASTEXITCODE). Revisa la conexion."
} else {
    Write-Host "    El ejecutable responde correctamente."
}

# ── 3. Instalador ───────────────────────────────────────────────────────────
Write-Step "Compilando el instalador con Inno Setup"
$Iscc = "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { $Iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
# winget instala Inno Setup por usuario en algunas maquinas (visto en la
# maquina de build), no bajo Program Files.
if (-not (Test-Path $Iscc)) { $Iscc = "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) {
    throw "No se encuentra Inno Setup. Instalalo con: winget install JRSoftware.InnoSetup"
}

& $Iscc "/DAppVersion=$Version" "installer\MXPDownloader.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallo" }
if (-not (Test-Path $InstallerPath)) { throw "No se genero el instalador en $InstallerPath" }

$SizeMB = [math]::Round((Get-Item $InstallerPath).Length / 1MB, 1)
Write-Host "    $InstallerName ($SizeMB MB)"

# ── 4. Checksum ─────────────────────────────────────────────────────────────
# El updater compara este hash antes de ejecutar el instalador descargado.
# Sin el, la app estaria ejecutando lo que le llegue por la red sin comprobar.
Write-Step "Generando SHA256SUMS.txt"
$Hash = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLower()
$SumsPath = Join-Path $ProjectRoot "dist\installer\SHA256SUMS.txt"
"$Hash  $InstallerName" | Out-File -FilePath $SumsPath -Encoding utf8 -NoNewline
Write-Host "    $Hash"

# ── 5. Publicacion ──────────────────────────────────────────────────────────
if ($SkipPublish) {
    Write-Step "Listo (sin publicar)"
    Write-Host "    Instalador: $InstallerPath"
    Write-Host ""
    Write-Host "    Para publicarlo:  .\scripts\release.ps1 -Notes ""...""" -ForegroundColor DarkGray
    exit 0
}

Write-Step "Publicando el release $Tag en GitHub"
$Repo = (py "-$PyVersion" -c "import sys; sys.path.insert(0, '.'); from mxp_common.version import GITHUB_REPO; print(GITHUB_REPO)").Trim()

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "No se encuentra gh. Instalalo con: winget install GitHub.cli"
}

if (-not $Notes) {
    $Notes = "Version $Version de MXP Downloader."
}

gh release create $Tag $InstallerPath $SumsPath --repo $Repo --title "MXP Downloader $Version" --notes $Notes
if ($LASTEXITCODE -ne 0) { throw "gh release create fallo" }

Write-Step "Publicado"
Write-Host "    https://github.com/$Repo/releases/tag/$Tag"
Write-Host ""
Write-Host "    Los usuarios con una version anterior veran el aviso de" -ForegroundColor DarkGray
Write-Host "    actualizacion la proxima vez que abran la app (se comprueba" -ForegroundColor DarkGray
Write-Host "    como maximo una vez cada 6 horas)." -ForegroundColor DarkGray
