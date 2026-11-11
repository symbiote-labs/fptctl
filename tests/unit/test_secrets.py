import keyring
import keyring.errors
import pytest

from fpt.errors import AuthError
from fpt.secrets import SERVICE, KeyringStore, MemoryStore


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    data: dict[tuple[str, str], str] = {}

    def delete(service: str, user: str) -> None:
        if (service, user) not in data:
            raise keyring.errors.PasswordDeleteError("not found")
        del data[(service, user)]

    monkeypatch.setattr(keyring, "get_password", lambda s, u: data.get((s, u)))
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: data.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "delete_password", delete)
    return data


def test_memory_store_round_trip() -> None:
    store = MemoryStore({"a": "1"})
    assert store.get("a") == "1"
    assert store.get("b") is None
    store.set("b", "2")
    assert store.get("b") == "2"
    store.delete("b")
    store.delete("b")  # deleting a missing secret is not an error
    assert store.get("b") is None


def test_keyring_store_uses_the_fpt_service(fake_keyring: dict[tuple[str, str], str]) -> None:
    store = KeyringStore()
    store.set("studio", "s3cret")
    assert fake_keyring == {(SERVICE, "studio"): "s3cret"}
    assert store.get("studio") == "s3cret"
    store.delete("studio")
    assert store.get("studio") is None


def test_keyring_store_delete_of_missing_secret_is_silent(
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    KeyringStore().delete("never-stored")


def test_keyring_failure_becomes_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(service: str, user: str) -> str:
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr(keyring, "get_password", broken)
    with pytest.raises(AuthError, match="FPT_API_KEY"):
        KeyringStore().get("studio")
