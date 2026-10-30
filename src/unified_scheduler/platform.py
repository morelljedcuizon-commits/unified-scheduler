"""Small Windows integration helpers; no shell command execution."""
import os
from pathlib import Path
import subprocess
import sys


def set_startup(enabled, data_dir=None):
    if os.name != "nt":
        if enabled:
            raise RuntimeError("Start with Windows is available on Windows only.")
        return
    import winreg
    key_name = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_name) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                args = [sys.executable, "--minimized"]
            else:
                interpreter = Path(sys.executable).with_name("pythonw.exe")
                args = [str(interpreter if interpreter.exists() else sys.executable), "-m", "unified_scheduler", "--minimized"]
            if data_dir:
                args.extend(["--data-dir", str(Path(data_dir).resolve())])
            winreg.SetValueEx(key, "UnifiedScheduler", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
        else:
            try:
                winreg.DeleteValue(key, "UnifiedScheduler")
            except FileNotFoundError:
                pass
