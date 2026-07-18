# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DouyinDownloader GUI.

构建产物：dist/DouyinDownloader/ 目录（含 .exe 和所有依赖）。
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Playwright：把整个包的数据（含 node driver）打进去
for module in ("playwright", "playwright._impl", "playwright.driver"):
    try:
        d, b, h = collect_all(module)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# tqdm 进度条
try:
    d, b, h = collect_all("tqdm")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

# Tkinter 通常系统自带，但加上保险
hiddenimports += ["tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"]

a = Analysis(
    ["douyin_dl/gui/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "PIL",
        "pandas",
        "pytest",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DouyinDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用，无控制台窗口
    disable_windowed_traceback=False,
    icon=None,  # 暂无图标，后续可加 assets/icon.ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DouyinDownloader",
)
