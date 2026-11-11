"""Secret storage: the OS keychain in production, memory in tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from fpt.errors import AuthError

SERVICE = "fpt"


class SecretStore(Protocol):
    def get(self, profile: str) -> str | None: ...

    def set(self, profile: str, secret: str) -> None: ...

    def delete(self, profile: str) -> None: ...


class MemoryStore:
    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self._data: dict[str, str] = dict(initial or {})

    def get(self, profile: str) -> str | None:
        return self._data.get(profile)

    def set(self, profile: str, secret: str) -> None:
        self._data[profile] = secret

    def delete(self, profile: str) -> None:
        self._data.pop(profile, None)


def _unavailable(exc: Exception) -> AuthError:
    return AuthError(
        f"The system keychain is unavailable ({exc}). "
        "Set FPT_SITE, FPT_SCRIPT_NAME and FPT_API_KEY instead.",
        {"exception": type(exc).__name__},
    )


class KeyringStore:
    def get(self, profile: str) -> str | None:
        import keyring
        import keyring.errors

        try:
            return keyring.get_password(SERVICE, profile)
        except keyring.errors.KeyringError as exc:
            raise _unavailable(exc) from exc

    def set(self, profile: str, secret: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(SERVICE, profile, secret)
        except keyring.errors.KeyringError as exc:
            raise _unavailable(exc) from exc

    def delete(self, profile: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(SERVICE, profile)
        except keyring.errors.PasswordDeleteError:
            return
        except keyring.errors.KeyringError as exc:
            raise _unavailable(exc) from exc
