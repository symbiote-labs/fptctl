"""Named site profiles, stored as TOML. Secrets are never written here."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

from fpt.errors import UsageError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

AUTH_TYPES: tuple[str, ...] = ("script", "user", "session")
_OPTIONAL_FIELDS = ("script_name", "login", "http_proxy", "ca_certs")


@dataclass(frozen=True)
class Profile:
    name: str
    site: str
    auth: str
    script_name: str | None = None
    login: str | None = None
    http_proxy: str | None = None
    ca_certs: str | None = None

    @property
    def identity(self) -> str | None:
        return self.script_name if self.auth == "script" else self.login


@dataclass(frozen=True)
class Config:
    default: str | None = None
    profiles: Mapping[str, Profile] = field(default_factory=dict)

    def get(self, name: str) -> Profile | None:
        return self.profiles.get(name)

    def with_profile(self, profile: Profile) -> Config:
        profiles = {**self.profiles, profile.name: profile}
        return Config(default=self.default or profile.name, profiles=profiles)

    def without_profile(self, name: str) -> Config:
        self._require(name)
        profiles = {key: value for key, value in self.profiles.items() if key != name}
        default = self.default
        if default == name:
            default = next(iter(sorted(profiles)), None)
        return Config(default=default, profiles=profiles)

    def with_default(self, name: str) -> Config:
        self._require(name)
        return Config(default=name, profiles=self.profiles)

    def _require(self, name: str) -> None:
        if name not in self.profiles:
            raise UsageError(f"No profile named '{name}'. Run `fpt auth list`.")


def default_config_path(environ: Mapping[str, str]) -> Path:
    override = environ.get("FPT_CONFIG")
    if override:
        return Path(override)
    base = environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "fpt" / "config.toml"


def _profile_from(name: str, body: Any, path: Path) -> Profile:
    if not isinstance(body, dict) or not isinstance(body.get("site"), str):
        raise UsageError(f"Config file {path}: profile '{name}' needs a 'site' string.")
    if body.get("auth") not in AUTH_TYPES:
        raise UsageError(
            f"Config file {path}: profile '{name}' needs 'auth' set to one of "
            f"{', '.join(AUTH_TYPES)}."
        )
    optional = {key: body.get(key) for key in _OPTIONAL_FIELDS}
    return Profile(name=name, site=body["site"], auth=body["auth"], **optional)


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"Cannot read config file {path}: {exc}") from exc
    profiles = {
        name: _profile_from(name, body, path) for name, body in raw.get("profiles", {}).items()
    }
    return Config(default=raw.get("default"), profiles=profiles)


def _profile_to(profile: Profile) -> dict[str, str]:
    body = {"site": profile.site, "auth": profile.auth}
    for key in _OPTIONAL_FIELDS:
        value = getattr(profile, key)
        if value is not None:
            body[key] = value
    return body


def save_config(config: Config, path: Path) -> None:
    document: dict[str, Any] = {}
    if config.default:
        document["default"] = config.default
    document["profiles"] = {
        name: _profile_to(profile) for name, profile in sorted(config.profiles.items())
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(tomli_w.dumps(document), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
