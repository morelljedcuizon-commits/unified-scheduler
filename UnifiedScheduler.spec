# Build on Windows: python -m PyInstaller --clean --noconfirm UnifiedScheduler.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

project_root = Path(SPECPATH)
datas = collect_data_files("googleapiclient") + collect_data_files("tzdata")
datas += copy_metadata("keyring")
datas += [(str(project_root / "assets" / "unified_scheduler_simple.ico"), "assets")]

a = Analysis(
    [str(project_root / "src" / "unified_scheduler" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["keyring.backends.Windows", "PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UnifiedScheduler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UnifiedScheduler")
