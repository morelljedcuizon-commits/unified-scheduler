"""Secrets live in the OS key store; a plaintext fallback is deliberately forbidden."""
import sys
import json
from threading import RLock
from uuid import uuid4


class CredentialError(RuntimeError):
    pass


class CredentialStore:
    SERVICE = "UnifiedScheduler"
    _PREFIX = "UnifiedScheduler:chunks:v1:"

    def __init__(self, service: str | None = None):
        self.service = service or self.SERVICE
        self._lock = RLock()

    def _parts(self, key, stored):
        if not stored or not stored.startswith(self._PREFIX):
            return []
        metadata = json.loads(stored[len(self._PREFIX):])
        generation, count = metadata["generation"], metadata["count"]
        if not isinstance(count, int) or not 1 <= count <= 2048 or len(generation) != 32 or not all(c in "0123456789abcdef" for c in generation):
            raise CredentialError("Stored credentials are damaged. Reconnect this calendar.")
        return [f"{key}::part:{generation}:{index}" for index in range(count)]

    def _backend(self):
        try:
            import keyring
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring
                backend = WinVaultKeyring()
            else:
                backend = keyring.get_keyring()
                module = type(backend).__module__.lower()
                if "plaintext" in module or "fail" in module or "null" in module or "chainer" in module:
                    raise CredentialError("A secure OS credential store is required to connect online calendars.")
            if backend.priority <= 0:
                raise CredentialError("The OS credential store is unavailable.")
            return backend
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("The OS credential store is unavailable. Local calendar features remain available.") from None

    def get(self, key: str) -> str | None:
        try:
            with self._lock:
                backend = self._backend()
                stored = backend.get_password(self.service, key)
                parts = self._parts(key, stored)
                if not parts:
                    return stored
                values = [backend.get_password(self.service, part) for part in parts]
                if any(value is None for value in values):
                    raise CredentialError("Stored credentials are incomplete. Reconnect this calendar.")
                return "".join(values)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Unable to read this calendar's credentials from the OS credential store.") from None

    def set(self, key: str, value: str):
        if not key or not isinstance(value, str):
            raise ValueError("A credential reference and string value are required.")
        if len(value) > 1024000:
            raise CredentialError("The credential is too large for the OS credential store.")
        try:
            with self._lock:
                backend = self._backend()
                previous = backend.get_password(self.service, key)
                old_parts = self._parts(key, previous)
                new_parts = []
                try:
                    if len(value) <= 500 and not value.startswith(self._PREFIX):
                        backend.set_password(self.service, key, value)
                    else:
                        # Windows generic credentials cap blobs at 2560 bytes. 500
                        # Unicode characters fit even when UTF-16 needs surrogate pairs.
                        chunks = [value[index:index + 500] for index in range(0, len(value), 500)]
                        generation = uuid4().hex
                        for index, chunk in enumerate(chunks):
                            part = f"{key}::part:{generation}:{index}"
                            backend.set_password(self.service, part, chunk)
                            new_parts.append(part)
                        metadata = self._PREFIX + json.dumps({"generation": generation, "count": len(chunks)})
                        backend.set_password(self.service, key, metadata)
                except Exception:
                    for part in new_parts:
                        try:
                            backend.delete_password(self.service, part)
                        except Exception:
                            pass
                    raise
                for part in old_parts:
                    try:
                        backend.delete_password(self.service, part)
                    except Exception:
                        pass  # New complete generation has already been committed.
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Unable to save credentials securely. No plaintext copy was written.") from None

    def delete(self, key: str):
        try:
            with self._lock:
                backend = self._backend()
                stored = backend.get_password(self.service, key)
                for part in self._parts(key, stored):
                    if backend.get_password(self.service, part) is not None:
                        backend.delete_password(self.service, part)
                if stored is not None:
                    backend.delete_password(self.service, key)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Unable to remove credentials from the OS credential store.") from None
