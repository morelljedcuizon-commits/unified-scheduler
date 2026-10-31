"""Exercise spec configuration branches and the archive's privacy boundary."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from unified_scheduler.google_oauth import GOOGLE_CLIENT_CONFIG_ENV
from unified_scheduler.providers.errors import ProviderError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_release", ROOT / "scripts/check_release.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def config():
    return {"installed": {"client_id": "synthetic.apps.googleusercontent.com",
                          "client_secret": "synthetic-desktop-value",
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": "https://oauth2.googleapis.com/token"}}


def run_spec(root, monkeypatch):
    import PyInstaller.utils.hooks
    monkeypatch.setattr(PyInstaller.utils.hooks, "collect_data_files", lambda _: [])
    monkeypatch.setattr(PyInstaller.utils.hooks, "copy_metadata", lambda _: [])
    analysis = Mock(return_value=SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[]))
    exe = Mock()
    namespace = {"SPECPATH": str(root), "Analysis": analysis, "PYZ": Mock(), "EXE": exe, "COLLECT": Mock()}
    exec(compile((ROOT / "UnifiedScheduler.spec").read_text(encoding="utf-8"), "UnifiedScheduler.spec", "exec"), namespace)
    return analysis.call_args.kwargs, exe.call_args.kwargs


def test_spec_only_packages_normalized_desktop_client(tmp_path, monkeypatch, config):
    monkeypatch.delenv(GOOGLE_CLIENT_CONFIG_ENV, raising=False)
    path = tmp_path / "local-config/google-oauth-client.json"
    path.parent.mkdir()
    config["refresh_token"] = "synthetic-never-package"
    path.write_text(json.dumps(config))
    (path.parent / "tokens.json").write_text("synthetic-private")
    analysis, executable = run_spec(tmp_path, monkeypatch)
    assert executable["icon"] == str(tmp_path / "assets/unified_scheduler_simple.ico")
    oauth_data = [(source, dest) for source, dest in analysis["datas"] if dest == "unified_scheduler/resources"]
    assert len(oauth_data) == 1
    staged = json.loads(Path(oauth_data[0][0]).read_text())
    assert staged == {"installed": config["installed"]}
    assert all("tokens.json" not in source and "local-config" not in source for source, _ in analysis["datas"])


def test_spec_does_not_reuse_stale_config_for_local_build(tmp_path, monkeypatch, config):
    monkeypatch.delenv(GOOGLE_CLIENT_CONFIG_ENV, raising=False)
    stale = tmp_path / "build/oauth-config/google-oauth-client.json"
    stale.parent.mkdir(parents=True)
    stale.write_text(json.dumps(config))
    analysis, _ = run_spec(tmp_path, monkeypatch)
    assert all(dest != "unified_scheduler/resources" for _, dest in analysis["datas"])


def test_spec_rejects_explicit_invalid_override_without_fallback(tmp_path, monkeypatch, config):
    default = tmp_path / "local-config/google-oauth-client.json"
    default.parent.mkdir()
    default.write_text(json.dumps(config))
    monkeypatch.setenv(GOOGLE_CLIENT_CONFIG_ENV, str(tmp_path / "missing.json"))
    with pytest.raises(ProviderError):
        run_spec(tmp_path, monkeypatch)


@pytest.fixture
def distribution(tmp_path):
    for name in ("UnifiedScheduler.exe", "LICENSE", "READ-ME.txt", "_internal/assets/unified_scheduler_simple.ico"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic")
    (tmp_path / "build-info.json").write_text(json.dumps({"google_client_included": False}))
    return tmp_path


def test_distribution_check_accepts_local_and_google_builds(distribution, config):
    assert checker.inspect_distribution(distribution) == []
    path = distribution / checker.CLIENT_RESOURCE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(config))
    (distribution / "build-info.json").write_text(json.dumps({"google_client_included": True}))
    assert checker.inspect_distribution(distribution) == []
    config["refresh_token"] = "synthetic-never-package"
    path.write_text(json.dumps(config))
    failures = checker.inspect_distribution(distribution)
    assert any("outside the normalized" in failure for failure in failures)
    assert "synthetic-never-package" not in repr(failures)


@pytest.mark.parametrize("relative", ["token.json", "workspace.sqlite3", "_internal/calendar.ics", "local-config/client.json", ".env"])
def test_distribution_rejects_private_files_without_printing_values(distribution, relative):
    path = distribution / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic-private-value")
    failures = checker.inspect_distribution(distribution)
    assert any(relative in failure for failure in failures)
    assert "synthetic-private-value" not in repr(failures)
