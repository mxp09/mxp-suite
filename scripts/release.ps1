<#
.SYNOPSIS
    Compila MXP Suite 4 y genera el instalador. Publica solo con -Publish.

.DESCRIPTION
      1. Herramientas oficiales verificadas (fetch-tools.ps1) si faltan
      2. App en release (Tauri, CRT estática)
      3. dist\app = exe + bin\ (ffmpeg, yt-dlp, deno, whisper)
      4. check-deps: ningún binario puede depender de DLL ajenas a Windows
      5. Autoprueba del exe ya montado
      6. Inno Setup -> dist\installer\MXP_Downloader_Setup_vX.Y.Z.exe + SHA256SUMS.txt
      7. (-Publish) release en GitHub
    Cualquier paso que falle detiene todo: no sale un instalador roto.
#>
[CmdletBinding()]
param([switch]$Publish, [string]$NotesFile = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Step "Versión"
$Version = (Select-String -Path "src-tauri\Cargo.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "    $Version"

if (-not (Test-Path "vendor\bin\whisper\whisper-cli.exe") -or -not (Test-Path "vendor\MicrosoftEdgeWebview2Setup.exe")) {
    Step "Descargando herramientas"
    & "$PSScriptRoot\fetch-tools.ps1"
}

Step "Compilando la app (release)"
if (-not (Test-Path "node_modules\@tauri-apps\cli")) { npm install --no-audit --no-fund | Out-Host }
npx tauri build --no-bundle | Out-Host
if ($LASTEXITCODE -ne 0) { throw "La compilación falló" }

Step "Montando dist\app"
$App = Join-Path $Root "dist\app"
Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$App\bin" | Out-Null
Copy-Item "src-tauri\target\release\mxp-suite.exe" "$App\MXP Suite.exe"
Copy-Item "vendor\bin\*" "$App\bin" -Recurse

Step "Comprobando dependencias de DLL"
& "$PSScriptRoot\check-deps.ps1" -Paths $App
if ($LASTEXITCODE -ne 0) { throw "Hay binarios que fallarían en un Windows limpio" }

Step "Autoprueba del exe montado"
$env:MXP_TOOLS_DIR = $null
& "$App\MXP Suite.exe" --self-test | Out-Host
if ($LASTEXITCODE -ne 0) { throw "La autoprueba falló" }

Step "Instalador"
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw "No se encuentra Inno Setup 6 (winget install JRSoftware.InnoSetup)" }
& $Iscc "/DAppVersion=$Version" "installer\MXPSuite.iss" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló" }
$Name = "MXP_Downloader_Setup_v$Version.exe"
$Installer = Join-Path $Root "dist\installer\$Name"
$Hash = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLower()
"$Hash  $Name" | Out-File -FilePath "dist\installer\SHA256SUMS.txt" -Encoding ascii -NoNewline
Write-Host ("    {0} ({1:N1} MB)  {2}" -f $Name, ((Get-Item $Installer).Length / 1MB), $Hash)

if ($Publish) {
    Step "Publicando v$Version"
    $notes = if ($NotesFile) { @("--notes-file", $NotesFile) } else { @("--notes", "MXP Suite $Version") }
    gh release create "v$Version" $Installer "dist\installer\SHA256SUMS.txt" --repo mxp09/mxp-suite --title "MXP Suite $Version" @notes
    if ($LASTEXITCODE -ne 0) { throw "gh release create falló" }
}
