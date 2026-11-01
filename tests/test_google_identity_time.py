"""Real signed-token validation with an isolated synthetic clock and RSA keys."""
from datetime import datetime, timezone
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import _helpers, crypt, jwt
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
import pytest

from unified_scheduler.database import Repository
from unified_scheduler.providers.errors import ProviderError
from unified_scheduler.providers.google import DesktopFlow, GoogleProvider, SCOPES


CLIENT = {"installed": {
    "client_id": "synthetic-clock-test.apps.googleusercontent.com",
    "client_secret": "synthetic-client-value",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}}
NOW = datetime(2026, 11, 1, 1, 0, 0)
NOW_SECONDS = int(NOW.replace(tzinfo=timezone.utc).timestamp())


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value


@pytest.fixture(scope="module")
def signing_keys():
    # Private keys exist only in memory and are generated anew for this test run.
    trusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    untrusted = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = trusted.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return (crypt.RSASigner(trusted, key_id="synthetic-signing-key"),
            crypt.RSASigner(untrusted, key_id="synthetic-signing-key"), public)


@pytest.fixture
def identity_session(tmp_path, monkeypatch, signing_keys):
    signer, untrusted_signer, public_key = signing_keys
    monkeypatch.setattr(_helpers, "utcnow", lambda: NOW)
    monkeypatch.setattr(id_token, "_fetch_certs", lambda request, url: {"synthetic-signing-key": public_key})
    monkeypatch.setattr("unified_scheduler.providers.google.secrets.token_urlsafe", lambda _: "synthetic-nonce")
    client = tmp_path / "synthetic-client.json"
    client.write_text(json.dumps(CLIENT), encoding="utf-8")
    repo = Repository(tmp_path / "synthetic-workspace.sqlite3")
    vault = MemoryCredentials()
    response = {}

    def local_server(flow, **kwargs):
        assert kwargs["nonce"] == "synthetic-nonce"
        return Credentials(
            "synthetic-access-token", refresh_token="synthetic-refresh-token",
            id_token=response["id_token"], scopes=list(SCOPES),
            client_id=CLIENT["installed"]["client_id"],
            client_secret=CLIENT["installed"]["client_secret"],
            token_uri=CLIENT["installed"]["token_uri"],
        )

    monkeypatch.setattr(DesktopFlow, "run_local_server", local_server)

    def authorize(overrides=None, *, invalid_signature=False):
        claims = {
            "iss": "https://accounts.google.com", "aud": CLIENT["installed"]["client_id"],
            "sub": "synthetic-person", "email": "person@example.invalid", "email_verified": True,
            "nonce": "synthetic-nonce", "iat": NOW_SECONDS, "exp": NOW_SECONDS + 3600,
        }
        claims.update(overrides or {})
        response["id_token"] = jwt.encode(untrusted_signer if invalid_signature else signer, claims).decode("utf-8")
        return GoogleProvider(repo, vault).connect(str(client))

    yield authorize, repo, vault, response
    repo.close()


@pytest.mark.parametrize("seconds_ahead", [0, 3, 60])
def test_signed_identity_accepts_small_clock_difference(identity_session, seconds_ahead):
    authorize, repo, vault, _ = identity_session
    account = authorize({"iat": NOW_SECONDS + seconds_ahead})
    assert repo.get_account(account.id) is not None
    assert len(vault.values) == 1
    assert "id_token" not in json.loads(next(iter(vault.values.values())))


@pytest.mark.parametrize("claims", [
    {"iat": NOW_SECONDS + 61},
    {"iat": NOW_SECONDS - 3600, "exp": NOW_SECONDS - 61},
])
def test_signed_identity_rejects_clock_difference_outside_tolerance(identity_session, claims):
    authorize, repo, vault, response = identity_session
    with pytest.raises(ProviderError, match="select Sync now") as error:
        authorize(claims)
    assert repo.list_accounts() == []
    assert vault.values == {}
    assert response["id_token"] not in str(error.value)


@pytest.mark.parametrize("claims", [
    {"aud": "another-app.apps.googleusercontent.com"},
    {"nonce": "another-request"},
    {"iss": "https://untrusted.example.invalid"},
])
def test_clock_tolerance_preserves_identity_boundaries(identity_session, claims):
    authorize, repo, vault, response = identity_session
    with pytest.raises(ProviderError) as error:
        authorize({"iat": NOW_SECONDS + 3, **claims})
    assert "Sync now" not in str(error.value)
    assert repo.list_accounts() == []
    assert vault.values == {}
    assert response["id_token"] not in str(error.value)


def test_clock_tolerance_preserves_signature_verification(identity_session):
    authorize, repo, vault, response = identity_session
    with pytest.raises(ProviderError) as error:
        authorize({"iat": NOW_SECONDS + 3}, invalid_signature=True)
    assert "Sync now" not in str(error.value)
    assert repo.list_accounts() == []
    assert vault.values == {}
    assert response["id_token"] not in str(error.value)
