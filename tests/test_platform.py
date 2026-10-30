"""Check Windows startup commands without modifying the user's registry."""
import sys
from types import SimpleNamespace

from unified_scheduler import platform


def test_startup_keeps_explicit_workspace_and_quotes_paths(monkeypatch, tmp_path):
    class Key:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass

    written, removed = [], []
    registry = SimpleNamespace(
        HKEY_CURRENT_USER="user", REG_SZ=1,
        CreateKey=lambda *_: Key(),
        SetValueEx=lambda *args: written.append(args),
        DeleteValue=lambda *args: removed.append(args),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(platform.os, "name", "nt")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Unified Scheduler\UnifiedScheduler.exe")
    workspace = tmp_path / "private workspace"
    platform.set_startup(True, workspace)
    command = written[0][-1]
    assert command.startswith('"C:\\Program Files\\Unified Scheduler\\UnifiedScheduler.exe"')
    assert '--minimized --data-dir "' in command
    assert str(workspace.resolve()) in command
    platform.set_startup(False, workspace)
    assert removed[0][1] == "UnifiedScheduler"
