"""App-owned OAuth setup uses only the intended Desktop client, never user data."""
import json
from unittest.mock import Mock

import pytest

from unified_scheduler import google_oauth
from unified_scheduler.database import Repository
from unified_scheduler.providers.errors import ProviderError
from unified_scheduler.providers.google import GoogleProvider


@pytest.fixture
def config():
    return {"installed": {
        "client_id": "test.apps.googleusercontent.com",
        "client_secret": "synthetic-desktop-client",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}


@pytest.fixture
def package_dir(tmp_path, monkeypatch):
    package = tmp_path / "src" / "unified_scheduler"
    package.mkdir(parents=True)
    monkeypatch.setattr(google_oauth, "_PACKAGE_DIR", package)
    monkeypatch.delenv(google_oauth.GOOGLE_CLIENT_CONFIG_ENV, raising=False)
    monkeypatch.setattr(google_oauth.sys, "frozen", False, raising=False)
    return package


def write_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8-sig")
    return path


def test_packaged_client_works_from_another_directory(package_dir, config, tmp_path, monkeypatch):
    bundled = write_config(package_dir / "resources" / "google-oauth-client.json", config)
    monkeypatch.setattr(google_oauth.sys, "frozen", True)
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert google_oauth.resolve_google_client_config_path("missing-legacy.json") == bundled
    assert google_oauth.load_google_client_config() == config


def test_source_client_and_legacy_fallback(package_dir, config, tmp_path, monkeypatch):
    legacy = write_config(tmp_path / "old-client.json", config)
    assert google_oauth.resolve_google_client_config_path(str(legacy)) == legacy
    source = write_config(tmp_path / "local-config" / "google-oauth-client.json", config)
    assert google_oauth.resolve_google_client_config_path(str(legacy)) == source
    write_config(package_dir / "resources" / "google-oauth-client.json", config)
    assert google_oauth.resolve_google_client_config_path(str(legacy)) != source


def test_frozen_app_does_not_load_development_client(package_dir, config, tmp_path, monkeypatch):
    write_config(tmp_path / "local-config" / "google-oauth-client.json", config)
    monkeypatch.setattr(google_oauth.sys, "frozen", True)
    assert google_oauth.resolve_google_client_config_path() is None


def test_explicit_override_wins_and_invalid_override_does_not_fall_back(package_dir, config, tmp_path, monkeypatch):
    write_config(package_dir / "resources" / "google-oauth-client.json", config)
    override = write_config(tmp_path / "override.json", config)
    monkeypatch.setenv(google_oauth.GOOGLE_CLIENT_CONFIG_ENV, str(override))
    assert google_oauth.resolve_google_client_config_path() == override
    override.write_text("not json: private-value", encoding="utf-8")
    with pytest.raises(ProviderError, match="invalid or unreadable") as error:
        google_oauth.load_google_client_config()
    assert "private-value" not in str(error.value)
    assert str(override) not in str(error.value)
    monkeypatch.setenv(google_oauth.GOOGLE_CLIENT_CONFIG_ENV, str(tmp_path / "missing.json"))
    with pytest.raises(ProviderError, match="invalid or unreadable"):
        google_oauth.load_google_client_config()


@pytest.mark.parametrize("payload", [
    None, [], {}, {"web": {}}, {"type": "service_account"},
    {"installed": None}, {"installed": []}, {"installed": {"client_id": 42}},
])
def test_non_desktop_configs_are_rejected(tmp_path, payload):
    with pytest.raises(ProviderError, match="invalid or unreadable"):
        google_oauth.read_google_client_config(write_config(tmp_path / "config.json", payload))


@pytest.mark.parametrize("field,value", [
    ("client_id", "test.invalid"), ("client_id", " test.apps.googleusercontent.com"),
    ("client_secret", None), ("client_secret", ""), ("client_secret", []),
    ("auth_uri", "https://attacker.invalid/authorize"),
    ("token_uri", "https://attacker.invalid/token"),
])
def test_invalid_fields_cannot_reach_oauth(tmp_path, config, field, value):
    config["installed"][field] = value
    with pytest.raises(ProviderError):
        google_oauth.read_google_client_config(write_config(tmp_path / "config.json", config))


def test_config_only_retains_desktop_oauth_fields(tmp_path, config):
    original = json.loads(json.dumps(config))
    config["refresh_token"] = "unrelated-private-token"
    config["installed"]["private_key"] = "unrelated-private-key"
    config["installed"]["project_id"] = "not-needed-for-signin"
    assert google_oauth.read_google_client_config(write_config(tmp_path / "config.json", config)) == original
    config["web"] = {"client_secret": "server-secret"}
    with pytest.raises(ProviderError):
        google_oauth.read_google_client_config(write_config(tmp_path / "mixed.json", config))


def test_missing_config_never_opens_browser_or_changes_accounts(package_dir, tmp_path, monkeypatch):
    factory = Mock(side_effect=AssertionError("Must not start OAuth without a client"))
    monkeypatch.setattr("unified_scheduler.providers.google.DesktopFlow.from_client_config", factory)
    vault = Mock()
    repo = Repository(tmp_path / "workspace.sqlite3")
    try:
        provider = GoogleProvider(repo, vault)
        assert repo.list_accounts() == []
        with pytest.raises(ProviderError, match="not configured in this build"):
            provider.connect()
        assert repo.list_accounts() == []
        assert repo.list_cached_events() == []
        factory.assert_not_called()
        assert not vault.mock_calls
    finally:
        repo.close()
