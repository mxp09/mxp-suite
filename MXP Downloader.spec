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

a = Analysis(
    ['MXPDOWNLOADER.pyw'],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'scipy', 'pandas', 'matplotlib',
        # yt-dlp queda FUERA del ejecutable a propósito. Empaquetado, el motor
        # se congelaba en la fecha del build y, como los sitios cambian su
        # extracción cada pocas semanas, acababa devolviendo 403 sin arreglo
        # posible salvo recompilar y redistribuir la app entera. Ahora vive en
        # %APPDATA%/MXP_Downloader/engine y se actualiza solo.
        'yt_dlp',
    ],
    noarchive=False,
    optimize=0,
)
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
