"""Exercise actual OAuth token parsing without a browser, network or real secrets."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from oauthlib.oauth2 import InvalidGrantError, MismatchingStateError, MissingTokenError
from oauthlib.oauth2.rfc6749.tokens import OAuth2Token

from unified_scheduler.database import Repository
from unified_scheduler.providers.errors import ProviderError
from unified_scheduler.providers.google import CALENDAR_SCOPES, DesktopFlow, GoogleProvider, ID_TOKEN_CLOCK_SKEW_SECONDS, SCOPES


CLIENT = {"installed": {
    "client_id": "synthetic-test.apps.googleusercontent.com",
    "client_secret": "synthetic-client-secret",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}}
LEGACY = [*SCOPES[:2], "https://www.googleapis.com/auth/calendar.readonly"]
CALLBACK = "https://127.0.0.1:12345/?code=synthetic-code&state=expected-state"


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value


def token_response(scopes):
    return {"access_token": "synthetic-access-token", "refresh_token": "synthetic-refresh-token",
            "id_token": "synthetic-id-token", "token_type": "Bearer", "expires_in": 3600,
            "scope": " ".join(scopes)}


def mock_exchange(monkeypatch, payload):
    requests_sent = []

    def send(session, request, **kwargs):
        assert request.url == CLIENT["installed"]["token_uri"]
        requests_sent.append(request)
        response = requests.Response()
        response.status_code = 400 if "error" in payload else 200
        response._content = json.dumps(payload).encode()
        response.headers["Content-Type"] = "application/json"
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return requests_sent


def new_flow():
    flow = DesktopFlow.from_client_config(CLIENT, scopes=list(SCOPES), autogenerate_code_verifier=True)
    flow.redirect_uri = "http://127.0.0.1:12345/"
    flow.oauth2session.state = "expected-state"
    url, _ = flow.authorization_url(nonce="expected-nonce")
    query = parse_qs(urlsplit(url).query)
    assert set(query["scope"][0].split()) == set(SCOPES)
    assert query["code_challenge_method"] == ["S256"]
    return flow


@pytest.mark.parametrize("granted", [list(SCOPES), LEGACY,
                                     [*SCOPES, "https://www.googleapis.com/auth/calendar.readonly"]])
def test_real_token_parser_accepts_scope_changes_for_application_validation(monkeypatch, granted):
    monkeypatch.delenv("OAUTHLIB_RELAX_TOKEN_SCOPE", raising=False)
    requests_sent = mock_exchange(monkeypatch, token_response(granted))
    flow = new_flow()

    token = flow.fetch_token(authorization_response=CALLBACK)

    assert len(requests_sent) == 1
    request_body = parse_qs(requests_sent[0].body)
    assert request_body["code_verifier"] == [flow.code_verifier]
    assert token["access_token"] == "synthetic-access-token"
    assert set(flow.credentials.granted_scopes) == set(granted)
    assert set(flow.credentials.scopes) == set(SCOPES)
    # Scope response handling must not alter process-wide OAuth security settings.
    import os
    assert "OAUTHLIB_RELAX_TOKEN_SCOPE" not in os.environ


def test_scope_handling_preserves_oauth_state_validation(monkeypatch):
    requests_sent = mock_exchange(monkeypatch, token_response(LEGACY))
    flow = new_flow()
    with pytest.raises(MismatchingStateError):
        flow.fetch_token(authorization_response=CALLBACK.replace("expected-state", "wrong-state"))
    assert requests_sent == []


@pytest.mark.parametrize("warning_kind", ["plain", "ordinary-dict", "unchanged-scopes",
                                          "missing-metadata", "warning-subclass"])
def test_scope_handling_does_not_swallow_unrelated_or_malformed_warnings(monkeypatch, warning_kind):
    requests_sent = mock_exchange(monkeypatch, token_response(LEGACY))
    flow = new_flow()
    warning_type = UserWarning if warning_kind == "warning-subclass" else Warning
    warning = warning_type("Synthetic unrelated token hook warning")
    if warning_kind != "plain":
        scopes = list(SCOPES) if warning_kind == "unchanged-scopes" else LEGACY
        payload = token_response(scopes)
        warning.token = (payload if warning_kind == "ordinary-dict"
                         else OAuth2Token(payload, old_scope=list(SCOPES)))
        if warning_kind != "missing-metadata":
            warning.old_scope, warning.new_scope = list(SCOPES), scopes

    def reject_response(response):
        raise warning

    flow.oauth2session.register_compliance_hook("access_token_response", reject_response)
    with pytest.raises(warning_type) as raised:
        flow.fetch_token(authorization_response=CALLBACK)

    assert raised.value is warning
    assert len(requests_sent) == 1
    assert flow.oauth2session.token == {}
    assert not flow.oauth2session.authorized


@pytest.mark.parametrize("payload,error", [
    ({"error": "invalid_grant", "error_description": "synthetic-private-detail"}, InvalidGrantError),
    ({"token_type": "Bearer", "scope": " ".join(LEGACY)}, MissingTokenError),
])
def test_scope_handling_does_not_accept_other_invalid_token_responses(monkeypatch, payload, error):
    mock_exchange(monkeypatch, payload)
    flow = new_flow()
    with pytest.raises(error):
        flow.fetch_token(authorization_response=CALLBACK)


@pytest.fixture
def provider_session(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-client.json"
    path.write_text(json.dumps(CLIENT), encoding="utf-8")
    repo = Repository(tmp_path / "workspace.sqlite3")
    vault = MemoryCredentials()
    monkeypatch.setattr("unified_scheduler.providers.google.secrets.token_urlsafe", lambda _: "expected-nonce")
    claims = {"sub": "synthetic-person", "email": "person@example.invalid",
              "email_verified": True, "nonce": "expected-nonce"}

    def verify(token, request, audience, clock_skew_in_seconds):
        assert token == "synthetic-id-token"
        assert audience == CLIENT["installed"]["client_id"]
        assert clock_skew_in_seconds == ID_TOKEN_CLOCK_SKEW_SECONDS == 60
        return claims

    def local_server(flow, **kwargs):
        # Replace only the browser/loopback transport. Keep real token fetching,
        # OAuthlib parsing and Google credential construction intact.
        flow.redirect_uri = "http://127.0.0.1:12345/"
        flow.oauth2session.state = "expected-state"
        flow.authorization_url(nonce=kwargs["nonce"])
        flow.fetch_token(authorization_response=CALLBACK)
        return flow.credentials

    monkeypatch.setattr("unified_scheduler.providers.google.id_token.verify_oauth2_token", verify)
    monkeypatch.setattr(DesktopFlow, "run_local_server", local_server)
    yield GoogleProvider(repo, vault), str(path), claims
    repo.close()


@pytest.mark.parametrize("granted", [[], list(SCOPES[:2]), [*SCOPES[:2], CALENDAR_SCOPES[0]],
                                     [*SCOPES[:2], CALENDAR_SCOPES[1]]])
def test_actual_partial_token_response_is_rejected_without_saving(provider_session, monkeypatch, granted):
    provider, path, _ = provider_session
    mock_exchange(monkeypatch, token_response(granted))
    with pytest.raises(ProviderError, match="Calendar read access was not granted"):
        provider.connect(path)
    assert provider.credentials.values == {}
    assert provider.repo.list_accounts() == []


def test_scope_change_still_requires_valid_identity_nonce(provider_session, monkeypatch):
    provider, path, claims = provider_session
    claims["nonce"] = "wrong-nonce"
    mock_exchange(monkeypatch, token_response(LEGACY))
    with pytest.raises(ProviderError, match="identity could not be verified"):
        provider.connect(path)
    assert provider.credentials.values == {}
    assert provider.repo.list_accounts() == []


def test_legacy_response_can_connect_without_retaining_id_token(provider_session, monkeypatch, capsys):
    provider, path, _ = provider_session
    mock_exchange(monkeypatch, token_response(LEGACY))
    provider.connect(path)
    assert len(provider.repo.list_accounts()) == 1
    stored = json.loads(next(iter(provider.credentials.values.values())))
    assert "id_token" not in stored
    assert "synthetic-id-token" not in capsys.readouterr().out


def test_invalid_token_error_is_sanitized_before_ui(provider_session, monkeypatch, capsys):
    provider, path, _ = provider_session
    mock_exchange(monkeypatch, {"error": "invalid_grant", "error_description": "synthetic-private-detail"})
    with pytest.raises(ProviderError) as error:
        provider.connect(path)
    assert "synthetic-private-detail" not in str(error.value)
    output = capsys.readouterr()
    assert "synthetic-private-detail" not in output.out + output.err
    assert provider.credentials.values == {}
    assert provider.repo.list_accounts() == []
