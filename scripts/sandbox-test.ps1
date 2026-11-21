<#
.SYNOPSIS
    Prueba el instalador en Windows limpio (Windows Sandbox), escenario a escenario.

.DESCRIPTION
    Requiere Windows Sandbox activado (una vez, PowerShell como administrador):
      Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
    y reiniciar. Cada escenario abre un Sandbox nuevo (Windows sin nada), que se
    apaga solo al terminar; los resultados quedan en tests\sandbox\results\<escenario>.

.EXAMPLE
    .\scripts\sandbox-test.ps1                      # todos
    .\scripts\sandbox-test.ps1 -Scenarios clean     # uno
#>
param([string[]]$Scenarios = @("clean", "offline", "accents", "upgrade"))

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Sandbox = "$env:SystemRoot\System32\WindowsSandbox.exe"
if (-not (Test-Path $Sandbox)) { throw "Windows Sandbox no está activado. Mira la ayuda de este script (Get-Help $PSCommandPath)." }
if (-not (Get-ChildItem "$Root\dist\installer\MXP_Downloader_Setup_v4*.exe" -ErrorAction SilentlyContinue)) { throw "Falta el instalador: ejecuta antes scripts\release.ps1" }

# La 3.2.1 publicada, para el escenario de actualización.
$legacy = "$Root\dist\installer\legacy"
if ($Scenarios -contains "upgrade" -and -not (Get-ChildItem "$legacy\*.exe" -ErrorAction SilentlyContinue)) {
    New-Item -ItemType Directory -Force $legacy | Out-Null
    gh release download v3.2.1 --repo mxp09/mxp-suite --pattern "*.exe" --dir $legacy
}

foreach ($s in $Scenarios) {
    $res = "$Root\tests\sandbox\results\$s"
    Remove-Item -Recurse -Force $res -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $res | Out-Null
    $net = if ($s -eq "offline") { "Disable" } else { "Default" }
    $wsb = "$env:TEMP\mxp-$s.wsb"
    @"
<Configuration>
  <Networking>$net</Networking>
  <MemoryInMB>6144</MemoryInMB>
  <MappedFolders>
    <MappedFolder><HostFolder>$Root\dist\installer</HostFolder><SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\installer</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$Root\tests\sandbox</HostFolder><SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\tests</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$res</HostFolder><SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\out</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell.exe -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\tests\run-in-sandbox.ps1 -Scenario $s</Command></LogonCommand>
</Configuration>
"@ | Set-Content $wsb -Encoding UTF8

    Write-Host "`n==> Escenario '$s' (Windows limpio$(if ($net -eq 'Disable') {', sin red'}))" -ForegroundColor Cyan
    Start-Process $Sandbox $wsb
    $deadline = (Get-Date).AddMinutes(40)
    while (-not (Test-Path "$res\done.txt") -and (Get-Date) -lt $deadline) { Start-Sleep 10 }
    # Solo puede haber un Sandbox a la vez: esperar a que se cierre del todo.
    while (Get-Process WindowsSandboxClient, WindowsSandboxRemoteSession -ErrorAction SilentlyContinue) { Start-Sleep 5 }
    if (Test-Path "$res\summary.txt") { Get-Content "$res\summary.txt" } else { Write-Host "Sin resultados (¿se colgó?)" -ForegroundColor Red }
    if (Test-Path "$res\selftest.json") {
        $r = Get-Content "$res\selftest.json" -Raw | ConvertFrom-Json
        $r.checks | ForEach-Object { "  [{0}] {1}: {2}" -f $(if ($_.ok) { "OK" } else { "XX" }), $_.label, $_.detail }
    }
}
