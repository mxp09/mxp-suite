<#
.SYNOPSIS
    Descarga y verifica las herramientas oficiales que lleva el instalador.

.DESCRIPTION
    Deja en vendor\bin: ffmpeg.exe, ffprobe.exe, yt-dlp.exe y deno.exe.
    Cada archivo se comprueba contra el SHA-256 que publica su proyecto:
    si no coincide, el script falla y no queda nada a medias.
    Todos son binarios estáticos (no necesitan VC++ ni otras DLL); lo
    confirma scripts\check-deps.ps1.
#>
[CmdletBinding()]
param(
    # Rama estable de FFmpeg (BtbN publica "nX.Y-latest"). Subirla a mano.
    [string]$FFmpegBranch = "8.1"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest va 10x más rápido sin barra
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
$Bin = Join-Path $Root "vendor\bin"
$Tmp = Join-Path $Root "vendor\tmp"
New-Item -ItemType Directory -Force $Bin, $Tmp | Out-Null

function Get-File($Url, $Dest) {
    Write-Host "  $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
}

function Assert-Hash($File, $Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 $File).Hash
    if ($actual -ne $Expected.ToUpper()) {
        Remove-Item $File -Force
        throw "SHA-256 no coincide para $(Split-Path -Leaf $File): esperado $Expected, obtenido $actual"
    }
}

# Busca el hash de $Name en un archivo de sumas tipo "hash  nombre".
function Find-Hash($SumsFile, $Name) {
    foreach ($line in Get-Content $SumsFile) {
        $parts = $line -split '\s+', 2
        if ($parts.Count -eq 2 -and $parts[1].Trim().TrimStart('*') -eq $Name) { return $parts[0] }
    }
    throw "No hay hash publicado para $Name"
}

# ── yt-dlp ──
Write-Host "yt-dlp"
$yt = "https://github.com/yt-dlp/yt-dlp/releases/latest/download"
Get-File "$yt/SHA2-256SUMS" "$Tmp\yt-sums.txt"
Get-File "$yt/yt-dlp.exe" "$Tmp\yt-dlp.exe"
Assert-Hash "$Tmp\yt-dlp.exe" (Find-Hash "$Tmp\yt-sums.txt" "yt-dlp.exe")
Move-Item -Force "$Tmp\yt-dlp.exe" "$Bin\yt-dlp.exe"

# ── FFmpeg (BtbN, rama estable, estático GPL) ──
Write-Host "FFmpeg $FFmpegBranch"
$ff = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
$ffZip = "ffmpeg-n$FFmpegBranch-latest-win64-gpl-$FFmpegBranch.zip"
Get-File "$ff/checksums.sha256" "$Tmp\ff-sums.txt"
Get-File "$ff/$ffZip" "$Tmp\$ffZip"
Assert-Hash "$Tmp\$ffZip" (Find-Hash "$Tmp\ff-sums.txt" $ffZip)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead("$Tmp\$ffZip")
try {
    foreach ($name in "ffmpeg.exe", "ffprobe.exe") {
        $entry = $zip.Entries | Where-Object { $_.Name -eq $name } | Select-Object -First 1
        if (-not $entry) { throw "$name no está en $ffZip" }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, "$Bin\$name", $true)
    }
} finally { $zip.Dispose() }

# ── Deno ──
Write-Host "Deno"
$dn = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
Get-File "$dn.sha256sum" "$Tmp\deno.sha"
Get-File $dn "$Tmp\deno.zip"
# El .sha256sum de Deno viene en formato Get-FileHash ("Hash : A0C3...").
$denoHash = [regex]::Match((Get-Content -Raw "$Tmp\deno.sha"), '\b[0-9a-fA-F]{64}\b').Value
Assert-Hash "$Tmp\deno.zip" $denoHash
Expand-Archive -Force "$Tmp\deno.zip" $Tmp
Move-Item -Force "$Tmp\deno.exe" "$Bin\deno.exe"

# ── whisper.cpp (motor de transcripción), versión fijada con hash ──
# Se usa el binario oficial: en las pruebas fue 1,7x más rápido que compilarlo
# nosotros y elige solo la variante para cada procesador (ggml-cpu-*.dll).
Write-Host "whisper.cpp"
$wUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip"
$wSha = "49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a"
Get-File $wUrl "$Tmp\whisper.zip"
Assert-Hash "$Tmp\whisper.zip" $wSha
$wDir = Join-Path $Bin "whisper"
Remove-Item -Recurse -Force $wDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $wDir | Out-Null
$zip = [IO.Compression.ZipFile]::OpenRead("$Tmp\whisper.zip")
try {
    foreach ($e in $zip.Entries) {
        if ($e.Name -eq "whisper-cli.exe" -or ($e.Name -like "*.dll" -and ($e.Name -like "whisper*" -or $e.Name -like "ggml*"))) {
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, (Join-Path $wDir $e.Name), $true)
        }
    }
} finally { $zip.Dispose() }

# Runtime de Visual C++ junto a whisper-cli (despliegue app-local, permitido
# por Microsoft): sin esto, en un Windows limpio salía "falta VCOMP140.DLL".
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -property installationPath
$redist = Get-ChildItem "$vs\VC\Redist\MSVC\*\x64" -Directory | Select-Object -Last 1
if (-not $redist) { throw "No se encuentra VC\Redist en Visual Studio Build Tools" }
foreach ($dll in "Microsoft.VC143.OpenMP\vcomp140.dll", "Microsoft.VC143.CRT\msvcp140.dll",
                 "Microsoft.VC143.CRT\vcruntime140.dll", "Microsoft.VC143.CRT\vcruntime140_1.dll") {
    Copy-Item (Join-Path $redist.FullName $dll) $wDir
}

Remove-Item -Recurse -Force $Tmp
Write-Host ""
Get-ChildItem $Bin | ForEach-Object { "{0,-14} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }
