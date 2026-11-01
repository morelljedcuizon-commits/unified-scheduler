"""Google Desktop OAuth with PKCE and isolated, authoritative calendar polling."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import hashlib
import json
import logging
import random
import secrets
import time as clock
from zoneinfo import ZoneInfo

from google.auth.exceptions import InvalidValue, RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import AccessDeniedError
from oauthlib.oauth2.rfc6749.tokens import OAuth2Token
import google_auth_httplib2
import httplib2
import requests

from ..google_oauth import load_google_client_config, read_google_client_config
from ..models import Calendar, Event, SourceAccount, stable_event_id
from .errors import OfflineError, ProviderError, ReauthenticationRequired

CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                   "https://www.googleapis.com/auth/calendar.events.readonly")
SCOPES = ("openid", "https://www.googleapis.com/auth/userinfo.email", *CALENDAR_SCOPES)
MAX_PAGES = 200
MAX_EVENTS = 100_000
ID_TOKEN_CLOCK_SKEW_SECONDS = 60

# This library's localhost request logger includes the OAuth callback query.
# It must remain silent even if an embedding application enables INFO logging.
logging.getLogger("google_auth_oauthlib.flow").disabled = True


class DesktopFlow(InstalledAppFlow):
    def fetch_token(self, **kwargs):
        kwargs.setdefault("timeout", 30)
        try:
            return super().fetch_token(**kwargs)
        except Warning as warning:
            token = getattr(warning, "token", None)
            if (type(warning) is not Warning or not isinstance(token, OAuth2Token)
                    or not token.scope_changed
                    or not all(hasattr(warning, name) for name in ("old_scope", "new_scope"))):
                raise
            # OAuthlib has validated the token but stops when Google's returned
            # grants differ, including permissions from an earlier consent.
            # Keep the actual grants for _authorize's Calendar/identity checks.
            # OAuth state and PKCE validation remain in the normal exchange.
            self.oauth2session.token = token
            return token


def _serialized_credentials(credentials) -> str:
    # The signed ID token is verified once during login; refresh does not need it.
    payload = json.loads(credentials.to_json())
    payload.pop("id_token", None)
    return json.dumps(payload, separators=(",", ":"))


class BoundedRequest(Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 30
        return super().__call__(*args, **kwargs)


def _identifier(prefix: str, *parts: str) -> str:
    return prefix + ":" + hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def _date_value(value: dict, timezone: str) -> tuple[str, bool]:
    if value.get("date"):
        return date.fromisoformat(value["date"]).isoformat(), True
    stamp = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=ZoneInfo(value.get("timeZone", timezone)))
    return stamp.isoformat(), False


def normalize_event(raw: dict, account_id: str, calendar_id: str, timezone: str,
                    reminder_minutes: int | None = 30) -> Event | None:
    if raw.get("status") == "cancelled":
        return None
    if not raw.get("id") or not raw.get("start"):
        raise ProviderError("Google returned an event without its ID or start date. The previous cache was preserved.")
    try:
        start, all_day = _date_value(raw["start"], timezone)
        if raw.get("end"):
            end, _ = _date_value(raw["end"], timezone)
        else:
            end = (date.fromisoformat(start) + timedelta(days=1)).isoformat() if all_day else start
        original = raw.get("originalStartTime", {})
        occurrence = ""
        if original:
            original_value, original_all_day = _date_value(original, timezone)
            occurrence = (original_value if original_all_day else
                          datetime.fromisoformat(original_value).astimezone(dt_timezone.utc).isoformat())
        event_id = stable_event_id("google", account_id, calendar_id, str(raw["id"]), occurrence)
        return Event(id=event_id, source="google", account_id=account_id, calendar_id=calendar_id,
                     uid=raw.get("iCalUID", raw["id"]), title=raw.get("summary") or "Untitled event",
                     start=start, end=end, all_day=all_day, description=raw.get("description", ""),
                     location=raw.get("location", ""), url=raw.get("htmlLink", ""),
                     reminder_minutes=reminder_minutes)
    except (ValueError, KeyError, TypeError):
        raise ProviderError("Google returned an invalid event date. The previous cache was preserved.") from None


class GoogleProvider:
    def __init__(self, repo, credentials, *, service_factory=None, sleep=clock.sleep):
        self.repo, self.credentials = repo, credentials
        self.service_factory, self.sleep = service_factory, sleep

    @staticmethod
    def _read_config(path: str) -> dict:
        return read_google_client_config(path)

    def connect(self, client_config_path: str | None = None) -> SourceAccount:
        return self._authorize(client_config_path)

    def reconnect(self, account_id: str, client_config_path: str | None = None) -> SourceAccount:
        account = self.repo.get_account(account_id)
        if not account or account.kind != "google":
            raise ProviderError("This Google account no longer exists.")
        return self._authorize(client_config_path, expected_account_id=account_id)

    def _authorize(self, path: str | None, expected_account_id: str | None = None) -> SourceAccount:
        config = (self._read_config(path) if path else
                  load_google_client_config(self.repo.get_setting("google_client_config", "")))
        nonce = secrets.token_urlsafe(32)
        try:
            flow = DesktopFlow.from_client_config(config, scopes=list(SCOPES), autogenerate_code_verifier=True)
            credentials = flow.run_local_server(
                host="127.0.0.1", port=0, open_browser=True, timeout_seconds=180,
                authorization_prompt_message="",
                success_message="Unified Scheduler authorization received. You may close this browser tab.",
                access_type="offline", prompt="select_account consent", nonce=nonce,
            )
            if not credentials.id_token:
                raise ProviderError("Google did not return an account identity. Retry and allow the identity and calendar permissions.")
            try:
                claims = id_token.verify_oauth2_token(
                    credentials.id_token, BoundedRequest(), audience=config["installed"]["client_id"],
                    clock_skew_in_seconds=ID_TOKEN_CLOCK_SKEW_SECONDS,
                )
            except InvalidValue as error:
                if str(error).startswith(("Token used too early,", "Token expired,")):
                    raise ProviderError(
                        "Google sign-in could not verify your computer's time. Open Windows Settings > "
                        "Time & language > Date & time, select Sync now, then connect again."
                    ) from None
                raise ProviderError("Google's account identity could not be verified. Please try again.") from None
            if (not claims.get("sub") or not claims.get("email") or claims.get("email_verified") is not True
                    or claims.get("nonce") != nonce):
                raise ProviderError("Google's account identity could not be verified. Please try again.")
            granted = (credentials.granted_scopes if credentials.granted_scopes is not None
                       else credentials.scopes) or []
            # Earlier builds requested calendar.readonly. Google can return a
            # previously granted broader scope; retain those existing accounts.
            if (not set(CALENDAR_SCOPES).issubset(granted)
                    and "https://www.googleapis.com/auth/calendar.readonly" not in granted):
                raise ProviderError("Calendar read access was not granted. Please reconnect and allow the requested permissions.")
            account_id = _identifier("google", claims["sub"])
            if expected_account_id and account_id != expected_account_id:
                raise ProviderError("You selected a different Google account. Reconnect using the original account, or use Connect Google Account to add another.")
            previous = self.repo.get_account(account_id)
            key = "google-token:" + account_id
            account = SourceAccount(id=account_id, kind="google", label=claims["email"],
                                    identity=claims["sub"], credential_key=key,
                                    status="connected", last_sync=previous.last_sync if previous else "")
            self.credentials.set(key, _serialized_credentials(credentials))
            self.repo.save_account(account)
            return account
        except ProviderError:
            raise
        except AccessDeniedError:
            raise ProviderError("Google sign-in was not approved. You can try again. If Google says this app is restricted, contact the app publisher.") from None
        except (requests.RequestException, TransportError):
            raise OfflineError("Google authorization could not reach its servers. Check your connection and try again.") from None
        except Exception:
            # OAuth exception messages may contain authorization codes or full redirect URLs.
            raise ProviderError("Google sign-in was cancelled, timed out, or failed. Try Connect Google Account again. If Google says access is blocked, contact the app publisher.") from None

    def _load_credentials(self, account: SourceAccount) -> Credentials:
        payload = self.credentials.get(account.credential_key)
        if not payload:
            raise ReauthenticationRequired("Google credentials are missing. Reconnect this account.")
        try:
            credentials = Credentials.from_authorized_user_info(json.loads(payload))
        except (ValueError, TypeError, KeyError):
            raise ReauthenticationRequired("Google credentials are invalid. Reconnect this account.") from None
        if not credentials.valid:
            if not credentials.refresh_token:
                raise ReauthenticationRequired("Google authorization has expired. Reconnect this account.")
            try:
                credentials.refresh(BoundedRequest())
                self.credentials.set(account.credential_key, _serialized_credentials(credentials))
            except RefreshError as error:
                if getattr(error, "retryable", False):
                    raise OfflineError("Google is temporarily unavailable. Cached events remain available.") from None
                raise ReauthenticationRequired("Google authorization was revoked or expired. Reconnect this account.") from None
            except (TransportError, requests.RequestException, OSError):
                raise OfflineError("Google could not be reached. Cached events remain available.") from None
        return credentials

    def _service(self, credentials):
        if self.service_factory:
            return self.service_factory(credentials)
        transport = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=30))
        return build("calendar", "v3", http=transport, cache_discovery=False, static_discovery=True)

    def _execute(self, request):
        for attempt in range(4):
            try:
                return request.execute(num_retries=0)
            except HttpError as error:
                code = int(error.resp.status)
                try:
                    details = json.loads(error.content).get("error", {}).get("errors", [])
                    reasons = {item.get("reason") for item in details}
                except (ValueError, TypeError, AttributeError):
                    reasons = set()
                rate_limited = code == 429 or (code == 403 and bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}))
                if (rate_limited or code in (500, 502, 503, 504)) and attempt < 3:
                    self.sleep(min(8.0, 0.8 * (2 ** attempt) + random.random() * 0.3))
                    continue
                if code == 401:
                    raise ReauthenticationRequired("Google authorization is no longer valid. Reconnect this account.") from None
                if rate_limited:
                    raise ProviderError("Google is limiting requests. Cached events remain available; synchronization will retry later.") from None
                if code == 403:
                    raise ProviderError("Google denied calendar access. Check that Calendar API is enabled and this account has calendar permission.") from None
                raise ProviderError("Google could not complete synchronization. Cached events remain available; try again later.") from None
            except RefreshError:
                raise ReauthenticationRequired("Google authorization was revoked or expired. Reconnect this account.") from None
            except (TransportError, requests.RequestException, httplib2.HttpLib2Error, OSError):
                if attempt < 3:
                    self.sleep(0.8 * (2 ** attempt))
                    continue
                raise OfflineError("Google could not be reached. Check your connection; cached events remain available.") from None

    def _pages(self, resource, **params):
        token = None
        seen = set()
        for _ in range(MAX_PAGES):
            page = self._execute(resource.list(**params, **({"pageToken": token} if token else {})))
            yield from page.get("items", [])
            token = page.get("nextPageToken")
            if not token:
                return
            if token in seen:
                raise ProviderError("Google returned a repeated page. Cached events have been preserved.")
            seen.add(token)
        raise ProviderError("This account exceeds the synchronization page limit. Use a shorter synchronization range.")

    def sync(self, account: SourceAccount, start: date, end: date, timezone: str) -> int:
        credentials = self._load_credentials(account)
        service = self._service(credentials)
        try:
            old_calendars = {calendar.remote_id: calendar for calendar in self.repo.list_calendars(account.id)}
            staged = []
            remote_ids = set()
            count = 0
            minimum = datetime.combine(start, time.min, ZoneInfo(timezone)).isoformat()
            maximum = datetime.combine(end, time.min, ZoneInfo(timezone)).isoformat()
            reminder = self.repo.get_setting("default_reminder", 30)
            reminder = int(reminder) if reminder is not None else None
            for raw in self._pages(service.calendarList(), maxResults=250, showDeleted=False, showHidden=True):
                if raw.get("deleted") or not raw.get("id"):
                    continue
                remote_id = raw["id"]
                remote_ids.add(remote_id)
                previous = old_calendars.get(remote_id)
                calendar = Calendar(id=_identifier("gcal", account.id, remote_id), account_id=account.id,
                                    remote_id=remote_id, name=raw.get("summaryOverride", raw.get("summary", "Google Calendar")),
                                    color=previous.color if previous else raw.get("backgroundColor", "#4285F4"),
                                    enabled=previous.enabled if previous else True,
                                    writable=False)  # This release deliberately requests read-only scopes.
                events = None
                if calendar.enabled:
                    event_map = {}
                    for item in self._pages(service.events(), calendarId=remote_id, timeMin=minimum, timeMax=maximum,
                                            singleEvents=True, showDeleted=False, maxResults=2500, timeZone=timezone):
                        event = normalize_event(item, account.id, calendar.id, timezone, reminder)
                        if event:
                            event_map[event.id] = event
                            count += 1
                            if count > MAX_EVENTS:
                                raise ProviderError("The synchronization range contains too many events. Reduce the date window in Settings.")
                    events = list(event_map.values())
                staged.append((calendar, events))
            # Nothing is removed until every requested page has succeeded.
            if not self.repo.get_account(account.id):
                raise ProviderError("This Google account was disconnected while synchronization was running.")
            for calendar, events in staged:
                # A background fetch can overlap a user's visibility/color edit.
                latest = self.repo.get_calendar(calendar.id)
                if latest:
                    calendar = replace(calendar, color=latest.color, enabled=latest.enabled)
                self.repo.save_calendar(calendar)
                if events is not None:
                    self.repo.replace_cached_events(calendar.id, events)
            for remote_id, previous in old_calendars.items():
                if remote_id not in remote_ids:
                    self.repo.delete_calendar(previous.id)
            # AuthorizedHttp may have refreshed credentials during a request.
            self.credentials.set(account.credential_key, _serialized_credentials(credentials))
            return count
        finally:
            close = getattr(service, "close", None)
            if close:
                close()

    def disconnect(self, account_id: str):
        account = self.repo.get_account(account_id)
        if account:
            self.credentials.delete(account.credential_key)
            self.repo.delete_account(account_id)
