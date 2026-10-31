# Build on Windows: python -m PyInstaller --clean --noconfirm UnifiedScheduler.spec
import json
import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

project_root = Path(SPECPATH)
sys.path.insert(0, str(project_root / "src"))
from unified_scheduler.google_oauth import GOOGLE_CLIENT_CONFIG_ENV, read_google_client_config

datas = collect_data_files("googleapiclient") + collect_data_files("tzdata")
datas += copy_metadata("keyring")
datas += [(str(project_root / "assets" / "unified_scheduler_simple.ico"), "assets")]
datas += [(str(project_root / "LICENSE"), ".")]

# Include only the application's Desktop OAuth identity, never a developer's
# token files, database, Moodle URLs or the rest of local-config.
configured_path = os.environ.get(GOOGLE_CLIENT_CONFIG_ENV, "").strip()
client_path = Path(configured_path).expanduser() if configured_path else project_root / "local-config" / "google-oauth-client.json"
if configured_path or client_path.exists():
    client_config = read_google_client_config(client_path)
    staging_path = project_root / "build" / "oauth-config" / "google-oauth-client.json"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path.write_text(json.dumps(client_config, indent=2), encoding="utf-8")
    datas.append((str(staging_path), "unified_scheduler/resources"))
    print("Bundling the application's Google Desktop OAuth configuration.")
else:
    print("Google sign-in is not configured. Building for local calendars and Moodle; see README for Google release setup.")

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
    icon=str(project_root / "assets" / "unified_scheduler_simple.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UnifiedScheduler")
