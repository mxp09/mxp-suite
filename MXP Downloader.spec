# -*- mode: python ; coding: utf-8 -*-
"""
Build de MXP Downloader (PyInstaller, one-folder).

Este es el ÚNICO spec del proyecto. Antes convivían tres builds en conflicto
(este, un MXPDOWNLOADER.spec obsoleto en one-file y un build de Nuitka en
scripts/build_mxp.py) sin ninguna forma de saber cuál era el bueno.

Compilar:  pyinstaller --noconfirm "MXP Downloader.spec"
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
    StringStruct, VarFileInfo, VarStruct,
)

sys.path.insert(0, str(Path(SPECPATH)))
from mxp_common.version import (  # noqa: E402
    __version__, APP_NAME, COMPANY_NAME, COPYRIGHT, DESCRIPTION, version_info_4,
)

# ffmpeg NO se empaqueta: son 133 MB que dejarían el instalador enorme y que
# de todas formas hay que poder actualizar por separado. Lo descarga y verifica
# el instalador, y la app sabe reponerlo sola si falta.
datas = [('assets', 'assets')]
binaries = []
hiddenimports = []

tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# pillow-heif trae su propia libheif compilada (binario nativo) además de
# código Python — collect_all es necesario, un simple hiddenimports no
# arrastraría esa .dll y el soporte de HEIC/HEIF fallaría solo en el .exe
# congelado (funcionando bien al correr desde el código fuente).
tmp_ret = collect_all('pillow_heif')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis(
    ['MXPDOWNLOADER.pyw'],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # yt_dlp NO va en excludes, a propósito. El motor sigue viviendo fuera del
    # .exe, en %APPDATA%/MXP_Downloader/engine, y actualizándose solo — eso no
    # cambia. Lo que cambió es CÓMO se logra: antes se excluía del análisis
    # entero, así que PyInstaller nunca veía sus imports y no empaquetaba la
    # librería estándar (ni los paquetes opcionales) que necesita. En
    # producción salió como "ModuleNotFoundError: No module named 'optparse'",
    # y arreglado eso, el mismo problema volvió a aparecer con 'html.parser'
    # un paso más adelante — intentar mantener a mano la lista de todo lo que
    # yt_dlp importa es una fuente interminable de este mismo bug.
    #
    # Ahora se deja que Analysis vea yt_dlp (tiene que estar `pip install`ado
    # en el entorno donde se compila — solo para que el análisis lo encuentre,
    # nunca se ejecuta desde aquí) para que descubra TODO lo que de verdad
    # necesita: no solo la librería estándar completa, sino también sus
    # dependencias opcionales de terceros (mutagen, brotli, certifi,
    # pycryptodomex, websockets — instalar con
    # `pip install "yt-dlp[default]"`), que antes ni se consideraban y que
    # mejoran de verdad la compatibilidad con más sitios y códecs.
    # El propio código de yt_dlp se retira de `a.pure` más abajo, después del
    # análisis: así el .exe se queda sin él (sigue viviendo en el motor
    # externo) pero se lleva puesto todo lo que descubrió que hacía falta.
    excludes=['numpy', 'scipy', 'pandas', 'matplotlib'],
    noarchive=False,
    optimize=0,
)

# Fuera el código propio de yt_dlp (queda vivo en el motor externo
# actualizable) — pero solo eso: todo lo demás que Analysis descubrió al
# caminar sus imports (stdlib completa, mutagen, brotli, certifi,
# pycryptodomex, websockets...) se queda, porque el resto de la app puede
# necesitarlo igual y ya está resuelto y verificado.
a.pure = [entry for entry in a.pure if entry[0] != 'yt_dlp' and not entry[0].startswith('yt_dlp.')]

pyz = PYZ(a.pure)

# Recurso de versión de Windows, generado desde mxp_common/version.py para que
# la versión que muestra el .exe en Propiedades sea la misma que la de la app,
# la del instalador y la que compara el updater.
version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=tuple(int(p) for p in version_info_4().split('.')),
        prodvers=tuple(int(p) for p in version_info_4().split('.')),
        mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable('040a04b0', [
            StringStruct('CompanyName', COMPANY_NAME),
            StringStruct('FileDescription', DESCRIPTION),
            StringStruct('FileVersion', __version__),
            StringStruct('InternalName', APP_NAME),
            StringStruct('LegalCopyright', COPYRIGHT),
            StringStruct('OriginalFilename', 'MXP Downloader.exe'),
            StringStruct('ProductName', APP_NAME),
            StringStruct('ProductVersion', __version__),
        ])]),
        # 0x040a = español, 1200 = Unicode
        VarFileInfo([VarStruct('Translation', [0x040a, 1200])]),
    ],
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MXP Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo_transparente.ico'],
    version=version_resource,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MXP Downloader',
)
