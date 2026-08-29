# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Obtener ruta de customtkinter para incluir sus recursos
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)

datas = [
    ('assets', 'assets'),
    ('gui', 'gui'),
    ('core', 'core'),
    (ctk_path, 'customtkinter'),
    ('logo.png', '.'),
]

# Añadir binarios de ffmpeg si existen locales
if os.path.exists('assets/bin/ffmpeg.exe'):
    datas.append(('assets/bin/ffmpeg.exe', 'assets/bin'))
if os.path.exists('assets/bin/ffprobe.exe'):
    datas.append(('assets/bin/ffprobe.exe', 'assets/bin'))

a = Analysis(
    ['MXPDOWNLOADER.pyw'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pandas',
        'scipy',
        'pyarrow',
        'matplotlib',
        'openpyxl',
        'sqlalchemy',
        'sqlite3',
        'jedi',
        'IPython',
        'tornado',
        'notebook',
        'numpy.tests',
        'win32com',
        'fitz',
        'pdf2docx',
        'pytesseract',
        'docx2pdf',
        'docx',
        'numpy',
        'cv2'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MXPDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo_transparente.ico',
)
