<#
.SYNOPSIS
    Falla si algún .exe/.dll entregado importa una DLL que un Windows limpio no trae.

.DESCRIPTION
    Es la prueba que habría evitado el "no se encontró VCOMP140.DLL" de la 3.2.0:
    en el PC de desarrollo el VC++ Redistributable está instalado, así que nada
    falla allí. Aquí no se ejecuta nada: se leen las importaciones de cada
    binario (dumpbin /dependents) y se comparan con una lista de DLL que
    forman parte de Windows 10 1809 o posterior.

    Una DLL que no está en la lista y tampoco se entrega junto al binario hace
    fallar el script. Si es de Windows de verdad, se añade a $SystemDlls.
#>
param(
    [Parameter(Mandatory)] [string[]]$Paths
)
$ErrorActionPreference = "Stop"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -property installationPath
$dumpbin = Get-ChildItem "$vs\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe" | Select-Object -Last 1
if (-not $dumpbin) { throw "No se encuentra dumpbin.exe (Build Tools de Visual Studio)" }

# DLL del sistema presentes en cualquier Windows 10 1809+ x64.
$SystemDlls = @(
    'kernel32', 'kernelbase', 'ntdll', 'user32', 'gdi32', 'gdiplus', 'advapi32', 'shell32', 'shlwapi',
    'ole32', 'oleaut32', 'comctl32', 'comdlg32', 'ws2_32', 'wsock32', 'mswsock', 'iphlpapi', 'dnsapi',
    'bcrypt', 'bcryptprimitives', 'crypt32', 'ncrypt', 'secur32', 'sspicli', 'userenv', 'version',
    'winmm', 'dwmapi', 'uxtheme', 'imm32', 'setupapi', 'cfgmgr32', 'propsys', 'powrprof', 'psapi',
    'dbghelp', 'winhttp', 'wininet', 'urlmon', 'netapi32', 'mpr', 'rpcrt4', 'ucrtbase', 'msvcrt',
    'd3d9', 'd3d11', 'd3d12', 'dxgi', 'dxva2', 'mfplat', 'mf', 'mfreadwrite', 'evr', 'avrt',
    'opengl32', 'glu32', 'dwrite', 'd2d1', 'windowscodecs', 'mfuuid', 'strmiids', 'ksuser',
    'hid', 'wtsapi32', 'winspool.drv', 'msimg32', 'usp10', 'normaliz', 'pdh', 'wldap32', 'oleacc',
    'uiautomationcore', 'shcore', 'api-ms-win-*', 'ext-ms-win-*', 'coremessaging', 'mmdevapi',
    'ntoskrnl.exe', 'wintrust', 'cryptbase', 'msasn1', 'dhcpcsvc', 'fwpuclnt', 'nsi', 'rasapi32',
    'avicap32', 'combase', 'rstrtmgr'
)
# Las que causaron problemas reales: se nombran para que el error sea claro.
$Forbidden = @('vcruntime140', 'vcruntime140_1', 'msvcp140', 'vcomp140', 'concrt140', 'python3*')

function Test-SystemDll($name) {
    $base = [IO.Path]::GetFileNameWithoutExtension($name).ToLower()
    foreach ($pattern in $SystemDlls) {
        if ($base -like $pattern -or $name.ToLower() -like $pattern) { return $true }
    }
    return $false
}

$failures = 0
$files = foreach ($p in $Paths) {
    if (Test-Path $p -PathType Container) { Get-ChildItem $p -Include *.exe, *.dll -Recurse -File }
    else { Get-Item $p }
}

foreach ($file in $files) {
    $out = & $dumpbin.FullName /nologo /dependents $file.FullName
    $deps = $out | Where-Object { $_ -match '^\s+\S+\.(dll|DLL|drv|exe)\s*$' } | ForEach-Object { $_.Trim() }
    $bad = @()
    foreach ($dep in $deps) {
        $base = [IO.Path]::GetFileNameWithoutExtension($dep).ToLower()
        $isForbidden = $Forbidden | Where-Object { $base -like $_ }
        $shipped = Test-Path (Join-Path $file.DirectoryName $dep)
        if ($isForbidden -and -not $shipped) { $bad += "$dep (runtime de VC++/Python: no existe en un Windows limpio)" }
        elseif (-not $shipped -and -not (Test-SystemDll $dep)) { $bad += "$dep (no es de Windows y no se entrega)" }
    }
    if ($bad) {
        $failures++
        Write-Host "FALLA  $($file.Name)" -ForegroundColor Red
        $bad | ForEach-Object { Write-Host "         $_" -ForegroundColor Red }
    } else {
        Write-Host "OK     $($file.Name)  ($($deps.Count) DLL de Windows)"
    }
}

if ($failures) { Write-Host "`n$failures binario(s) con dependencias que faltarían en un PC limpio." -ForegroundColor Red; exit 1 }
Write-Host "`nTodos los binarios funcionan en un Windows limpio (solo DLL del sistema)."
