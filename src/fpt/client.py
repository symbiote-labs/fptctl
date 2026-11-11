"""Credential resolution and the only module that touches shotgun_api3."""

from __future__ import annotations

import functools
import inspect
import socket
import ssl
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.client import ProtocolError

from fpt import __version__
from fpt.config import Config
from fpt.errors import ApiFaultError, AuthError, FptError, NetworkError, UsageError
from fpt.secrets import SecretStore
from fpt.wire import dumps

ENV_SITE = "FPT_SITE"
ENV_SCRIPT_NAME = "FPT_SCRIPT_NAME"
ENV_API_KEY = "FPT_API_KEY"
ENV_LOGIN = "FPT_LOGIN"
ENV_PASSWORD = "FPT_PASSWORD"
ENV_SESSION_TOKEN = "FPT_SESSION_TOKEN"
ENV_PROFILE = "FPT_PROFILE"
ENV_HTTP_PROXY = "FPT_HTTP_PROXY"
ENV_CA_CERTS = "FPT_CA_CERTS"
ENV_TRACE_FILE = "FPT_TRACE_FILE"

SECRET_ARGUMENTS = frozenset(
    {"api_key", "password", "session_token", "auth_token", "user_password"}
)
REDACTED = "<redacted>"

_TRANSPORT_ERRORS = (ProtocolError, ConnectionError, TimeoutError, socket.gaierror, ssl.SSLError)


@dataclass(frozen=True)
class Credentials:
    site: str
    auth: str
    secret: str = field(repr=False)
    script_name: str | None = None
    login: str | None = None
    http_proxy: str | None = None
    ca_certs: str | None = None
    auth_token: str | None = field(default=None, repr=False)  # one-time 2FA code
    source: str = "env"

    @property
    def identity(self) -> str | None:
        return self.script_name if self.auth == "script" else self.login


def normalize_site(site: str) -> str:
    cleaned = site.strip().rstrip("/")
    if not cleaned:
        raise UsageError("The site URL is empty.")
    return cleaned if "://" in cleaned else f"https://{cleaned}"


def _from_env(environ: Mapping[str, str], site_flag: str | None) -> Credentials | None:
    script, key = environ.get(ENV_SCRIPT_NAME), environ.get(ENV_API_KEY)
    login, password = environ.get(ENV_LOGIN), environ.get(ENV_PASSWORD)
    token = environ.get(ENV_SESSION_TOKEN)
    if not any((script, key, login, password, token)):
        return None
    raw_site = site_flag or environ.get(ENV_SITE)
    if not raw_site:
        raise AuthError(f"{ENV_SITE} is required when credentials come from the environment.")
    site = normalize_site(raw_site)
    proxy, ca = environ.get(ENV_HTTP_PROXY), environ.get(ENV_CA_CERTS)
    if script or key:
        if not (script and key):
            raise AuthError(f"Set both {ENV_SCRIPT_NAME} and {ENV_API_KEY}.")
        return Credentials(site, "script", key, script_name=script, http_proxy=proxy, ca_certs=ca)
    if login or password:
        if not (login and password):
            raise AuthError(f"Set both {ENV_LOGIN} and {ENV_PASSWORD}.")
        return Credentials(site, "user", password, login=login, http_proxy=proxy, ca_certs=ca)
    assert token is not None
    return Credentials(site, "session", token, http_proxy=proxy, ca_certs=ca)


def _from_profile(
    name: str, config: Config, secrets: SecretStore, site_flag: str | None
) -> Credentials:
    profile = config.get(name)
    if profile is None:
        raise AuthError(f"No profile named '{name}'. Run `fpt auth list`.")
    secret = secrets.get(name)
    if not secret:
        raise AuthError(
            f"No stored secret for profile '{name}'. Run `fpt auth login --name {name}`."
        )
    return Credentials(
        site=normalize_site(site_flag or profile.site),
        auth=profile.auth,
        secret=secret,
        script_name=profile.script_name,
        login=profile.login,
        http_proxy=profile.http_proxy,
        ca_certs=profile.ca_certs,
        source=f"profile:{name}",
    )


def resolve_credentials(
    *,
    site_flag: str | None,
    profile_flag: str | None,
    environ: Mapping[str, str],
    config: Config,
    secrets: SecretStore,
) -> Credentials:
    if profile_flag:
        return _from_profile(profile_flag, config, secrets, site_flag)
    from_env = _from_env(environ, site_flag)
    if from_env is not None:
        return from_env
    name = environ.get(ENV_PROFILE) or config.default
    if name:
        return _from_profile(name, config, secrets, site_flag)
    raise AuthError(
        "No credentials found. Run `fpt auth login`, or set "
        f"{ENV_SITE}, {ENV_SCRIPT_NAME} and {ENV_API_KEY}."
    )


def bind_arguments(
    func: Callable[..., Any], args: Sequence[Any], kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    """Every parameter of `func` by name, defaults filled in, **kwargs merged in."""
    signature = inspect.signature(func)
    bound = signature.bind(*args, **kwargs)
    bound.apply_defaults()
    arguments: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        kind = signature.parameters[name].kind
        if kind is inspect.Parameter.VAR_KEYWORD:
            arguments.update(value)
        elif kind is inspect.Parameter.VAR_POSITIONAL:
            arguments[name] = list(value)
        else:
            arguments[name] = value
    return arguments


def redact(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {name: _redact_one(name, value) for name, value in arguments.items()}


def _redact_one(name: str, value: Any) -> Any:
    if name in SECRET_ARGUMENTS and value is not None:
        return REDACTED
    if name == "http_proxy" and isinstance(value, str) and "@" in value:
        # [user:pass@]host[:port]: keep the host, hide the credentials.
        return f"{REDACTED}@{value.rsplit('@', 1)[1]}"
    return value


def _trace(path: str | None, record: dict[str, Any]) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(dumps(record) + "\n")


class TracedClient:
    """The library client as commands see it: every public call traced, argument errors exit 2."""

    def __init__(self, client: Any, trace_path: str | None = None) -> None:
        self._client = client
        self._trace_path = trace_path

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._client, name)
        if name.startswith("_") or not callable(attribute):
            return attribute
        return functools.partial(self._call, name, attribute)

    def _call(self, name: str, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            arguments = bind_arguments(method, args, kwargs)
        except TypeError as exc:
            raise UsageError(f"{name}(): {exc}", {"exception": "TypeError"}) from exc
        _trace(self._trace_path, {"call": name, "args": redact(arguments)})
        try:
            return method(*args, **kwargs)
        except (ValueError, TypeError) as exc:
            details = {"exception": type(exc).__name__}
            raise UsageError(str(exc) or type(exc).__name__, details) from exc


def describe_call(method: str, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """The trace record of a call not made (`--dry-run`): defaults filled, secrets hidden."""
    import shotgun_api3

    try:
        arguments = bind_arguments(getattr(shotgun_api3.Shotgun, method), (None,), kwargs)
    except TypeError as exc:
        raise UsageError(f"{method}(): {exc}", {"exception": "TypeError"}) from exc
    arguments.pop("self", None)
    return {"call": method, "args": redact(arguments)}


def build_client(
    credentials: Credentials, *, sudo_as: str | None = None, trace_path: str | None = None
) -> TracedClient:
    import shotgun_api3

    kwargs: dict[str, Any] = {
        "http_proxy": credentials.http_proxy,
        "ca_certs": credentials.ca_certs,
        "sudo_as_login": sudo_as,
        "connect": False,
    }
    if credentials.auth == "script":
        kwargs.update(script_name=credentials.script_name, api_key=credentials.secret)
    elif credentials.auth == "user":
        kwargs.update(login=credentials.login, password=credentials.secret)
        if credentials.auth_token:
            kwargs["auth_token"] = credentials.auth_token
    else:
        kwargs.update(session_token=credentials.secret)
    construct = bind_arguments(shotgun_api3.Shotgun, (credentials.site,), kwargs)
    _trace(trace_path, {"construct": redact(construct)})
    client = shotgun_api3.Shotgun(credentials.site, **kwargs)
    client.add_user_agent(
        f"fpt/{__version__}"
    )  # fpt's own plumbing: made on the raw client, untraced
    return TracedClient(client, trace_path)


def translate_error(exc: Exception) -> FptError:
    if isinstance(exc, FptError):
        return exc
    import shotgun_api3
    import shotgun_api3.shotgun as sg
    from shotgun_api3.lib import httplib2

    message = str(exc) or type(exc).__name__
    details = {"exception": type(exc).__name__}
    # The 2FA / SSO / Oxygen faults subclass Fault, not AuthenticationFault, so list them.
    auth_faults = (
        sg.AuthenticationFault,
        sg.MissingTwoFactorAuthenticationFault,
        sg.UserCredentialsNotAllowedForSSOAuthenticationFault,
        sg.UserCredentialsNotAllowedForOxygenAuthenticationFault,
    )
    if isinstance(exc, auth_faults):
        return AuthError(message, details)
    if isinstance(exc, shotgun_api3.ShotgunError):
        return ApiFaultError(message, details)
    if isinstance(exc, (*_TRANSPORT_ERRORS, httplib2.HttpLib2Error)):
        return NetworkError(message, details)
    return FptError(message, details)


def public_methods() -> dict[str, str]:
    """Every public method of shotgun_api3.Shotgun and its signature, read at run time."""
    import shotgun_api3

    methods: dict[str, str] = {}
    for name, member in inspect.getmembers(shotgun_api3.Shotgun, callable):
        if name.startswith("_"):
            continue
        signature = inspect.signature(member)
        parameters = [p for p in signature.parameters.values() if p.name != "self"]
        methods[name] = str(signature.replace(parameters=parameters))
    return methods
