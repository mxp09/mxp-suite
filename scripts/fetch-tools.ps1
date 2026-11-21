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

Remove-Item -Recurse -Force $Tmp
Write-Host ""
Get-ChildItem $Bin | ForEach-Object { "{0,-14} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }
