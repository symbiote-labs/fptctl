import socket
import ssl
from typing import Any
from xmlrpc.client import ProtocolError

import pytest
import shotgun_api3

from fptctl import __version__
from fptctl.client import (
    Credentials,
    build_client,
    normalize_site,
    resolve_credentials,
    translate_error,
)
from fptctl.config import Config, Profile
from fptctl.errors import ApiFaultError, AuthError, FptError, NetworkError, UsageError
from fptctl.secrets import MemoryStore

STUDIO = Profile(name="studio", site="https://studio.example.com", auth="script", script_name="bot")
ARTIST = Profile(name="artist", site="https://studio.example.com", auth="user", login="ada")
CONFIG = Config().with_profile(STUDIO).with_profile(ARTIST)
SECRETS = MemoryStore({"studio": "studio-key", "artist": "ada-pw"})
SCRIPT_ENV = {
    "FPTCTL_SITE": "https://env.example.com",
    "FPTCTL_SCRIPT_NAME": "envbot",
    "FPTCTL_API_KEY": "env-key",
}


def resolve(
    env: dict[str, str] | None = None,
    *,
    site: str | None = None,
    profile: str | None = None,
    config: Config = CONFIG,
) -> Credentials:
    return resolve_credentials(
        site_flag=site, profile_flag=profile, environ=env or {}, config=config, secrets=SECRETS
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://x.example.com/", "https://x.example.com"),
        ("  x.example.com ", "https://x.example.com"),
        ("http://localhost:8080", "http://localhost:8080"),
    ],
)
def test_normalize_site(raw: str, expected: str) -> None:
    assert normalize_site(raw) == expected


def test_normalize_site_rejects_empty() -> None:
    with pytest.raises(UsageError):
        normalize_site("  ")


def test_default_profile_is_used_when_nothing_else_is_given() -> None:
    creds = resolve()
    assert creds == Credentials(
        site="https://studio.example.com",
        auth="script",
        secret="studio-key",
        script_name="bot",
        source="profile:studio",
    )
    assert creds.identity == "bot"


def test_env_credentials_beat_the_default_profile() -> None:
    creds = resolve(SCRIPT_ENV)
    assert (creds.site, creds.script_name, creds.secret, creds.source) == (
        "https://env.example.com",
        "envbot",
        "env-key",
        "env",
    )


def test_profile_flag_beats_env_credentials() -> None:
    creds = resolve(SCRIPT_ENV, profile="artist")
    assert (creds.auth, creds.login, creds.secret, creds.source) == (
        "user",
        "ada",
        "ada-pw",
        "profile:artist",
    )


def test_fpt_profile_env_selects_a_profile() -> None:
    assert resolve({"FPTCTL_PROFILE": "artist"}).source == "profile:artist"


def test_site_flag_overrides_site_from_any_source() -> None:
    assert resolve(site="other.example.com").site == "https://other.example.com"
    assert resolve(SCRIPT_ENV, site="other.example.com").site == "https://other.example.com"


def test_env_user_and_session_credentials() -> None:
    user = resolve({"FPTCTL_SITE": "x.example.com", "FPTCTL_LOGIN": "ada", "FPTCTL_PASSWORD": "pw"})
    assert (user.auth, user.login, user.secret) == ("user", "ada", "pw")
    session = resolve({"FPTCTL_SITE": "x.example.com", "FPTCTL_SESSION_TOKEN": "tok"})
    assert (session.auth, session.secret, session.identity) == ("session", "tok", None)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"FPTCTL_SITE": "x", "FPTCTL_API_KEY": "k"}, "FPTCTL_SCRIPT_NAME and FPTCTL_API_KEY"),
        ({"FPTCTL_SITE": "x", "FPTCTL_LOGIN": "ada"}, "FPTCTL_LOGIN and FPTCTL_PASSWORD"),
        ({"FPTCTL_SCRIPT_NAME": "b", "FPTCTL_API_KEY": "k"}, "FPTCTL_SITE"),
    ],
)
def test_incomplete_env_credentials_are_auth_errors(env: dict[str, str], message: str) -> None:
    with pytest.raises(AuthError, match=message):
        resolve(env, config=Config())


def test_no_credentials_anywhere_is_an_auth_error() -> None:
    with pytest.raises(AuthError, match="fptctl auth login"):
        resolve(config=Config())


def test_unknown_profile_is_an_auth_error() -> None:
    with pytest.raises(AuthError, match="No profile named 'nope'"):
        resolve(profile="nope")


def test_profile_without_stored_secret_is_an_auth_error() -> None:
    orphan = Config().with_profile(Profile(name="orphan", site="https://x", auth="session"))
    with pytest.raises(AuthError, match="No stored secret for profile 'orphan'"):
        resolve(config=orphan)


def test_secret_is_not_in_repr() -> None:
    assert "studio-key" not in repr(resolve())


class RecordingShotgun:
    instances: list["RecordingShotgun"] = []

    def __init__(self, base_url: str, **kwargs: Any) -> None:
        self.base_url = base_url
        self.kwargs = kwargs
        self.agents: list[str] = []
        RecordingShotgun.instances.append(self)

    def add_user_agent(self, agent: str) -> None:
        self.agents.append(agent)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[RecordingShotgun]:
    RecordingShotgun.instances = []
    monkeypatch.setattr(shotgun_api3, "Shotgun", RecordingShotgun)
    return RecordingShotgun.instances


def test_build_client_for_script_auth(recorded: list[RecordingShotgun]) -> None:
    client = build_client(resolve(), sudo_as="ada")
    assert len(recorded) == 1
    assert client.base_url == "https://studio.example.com"
    assert client.kwargs == {
        "script_name": "bot",
        "api_key": "studio-key",
        "http_proxy": None,
        "ca_certs": None,
        "sudo_as_login": "ada",
        "connect": False,
    }
    assert client.agents == [f"fptctl/{__version__}"]


def test_build_client_for_user_auth(recorded: list[RecordingShotgun]) -> None:
    build_client(resolve(profile="artist"))
    assert recorded[0].kwargs["login"] == "ada"
    assert recorded[0].kwargs["password"] == "ada-pw"
    assert "api_key" not in recorded[0].kwargs


def test_build_client_for_session_auth(recorded: list[RecordingShotgun]) -> None:
    build_client(resolve({"FPTCTL_SITE": "x.example.com", "FPTCTL_SESSION_TOKEN": "tok"}))
    assert recorded[0].kwargs["session_token"] == "tok"


def test_build_client_passes_proxy_ca_certs_and_one_time_code(
    recorded: list[RecordingShotgun],
) -> None:
    env = {
        "FPTCTL_SITE": "x.example.com",
        "FPTCTL_LOGIN": "ada",
        "FPTCTL_PASSWORD": "pw",
        "FPTCTL_HTTP_PROXY": "proxy:3128",
        "FPTCTL_CA_CERTS": "/etc/ca.pem",
    }
    from dataclasses import replace

    build_client(replace(resolve(env), auth_token="123456"))
    assert recorded[0].kwargs["http_proxy"] == "proxy:3128"
    assert recorded[0].kwargs["ca_certs"] == "/etc/ca.pem"
    assert recorded[0].kwargs["auth_token"] == "123456"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (shotgun_api3.AuthenticationFault("bad key"), AuthError),
        (shotgun_api3.shotgun.MissingTwoFactorAuthenticationFault("need 2fa"), AuthError),
        (
            shotgun_api3.shotgun.UserCredentialsNotAllowedForSSOAuthenticationFault("sso"),
            AuthError,
        ),
        (
            shotgun_api3.shotgun.UserCredentialsNotAllowedForOxygenAuthenticationFault("oxygen"),
            AuthError,
        ),
        (shotgun_api3.shotgun.ShotgunFileDownloadError("download failed"), ApiFaultError),
        (shotgun_api3.shotgun.ShotgunThumbnailNotReady("not ready"), ApiFaultError),
        (shotgun_api3.Fault("field does not exist"), ApiFaultError),
        (shotgun_api3.ShotgunError("bad arguments"), ApiFaultError),
        (ProtocolError("https://x", 503, "Service Unavailable", {}), NetworkError),  # type: ignore[arg-type]
        (ConnectionRefusedError("refused"), NetworkError),
        (TimeoutError("timed out"), NetworkError),
        (socket.gaierror("name not known"), NetworkError),
        (ssl.SSLError("handshake failed"), NetworkError),
    ],
)
def test_translate_error(exc: Exception, expected: type[FptError]) -> None:
    translated = translate_error(exc)
    assert type(translated) is expected
    assert translated.details["exception"] == type(exc).__name__


def test_translate_httplib2_error_is_network() -> None:
    from shotgun_api3.lib import httplib2

    assert type(translate_error(httplib2.ServerNotFoundError("no host"))) is NetworkError


def test_translate_error_passes_fpt_errors_through() -> None:
    original = UsageError("nope")
    assert translate_error(original) is original


def test_translate_unknown_error_is_unexpected() -> None:
    translated = translate_error(RuntimeError("surprise"))
    assert type(translated) is FptError
    assert translated.message == "surprise"
    assert translated.details == {"exception": "RuntimeError"}
