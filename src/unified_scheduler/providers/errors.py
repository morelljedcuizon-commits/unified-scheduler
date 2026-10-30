"""Safe, user-facing errors. Never include a provider response or private URL."""


class ProviderError(RuntimeError):
    """A deliberately sanitized error suitable for displaying in the UI."""


class ReauthenticationRequired(ProviderError):
    """The account must complete browser authorization again."""


class OfflineError(ProviderError):
    """The provider could not be reached; the previous cache remains valid."""

