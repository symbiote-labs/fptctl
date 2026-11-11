"""Per-invocation application context and its injectable dependencies."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from fptctl.client import ENV_TRACE_FILE, Credentials, build_client, resolve_credentials
from fptctl.config import Config, default_config_path, load_config
from fptctl.output import render, resolve_format
from fptctl.secrets import KeyringStore, SecretStore


@dataclass(frozen=True)
class Deps:
    """Everything fptctl takes from the outside world. Tests replace all of it."""

    environ: Mapping[str, str]
    config_path: Path
    secrets: SecretStore
    client_factory: Callable[..., Any]


def default_deps() -> Deps:
    return Deps(
        environ=os.environ,
        config_path=default_config_path(os.environ),
        secrets=KeyringStore(),
        client_factory=build_client,
    )


@dataclass(frozen=True)
class AppContext:
    deps: Deps
    profile: str | None = None
    site: str | None = None
    fmt: str | None = None
    sudo_as: str | None = None
    color: bool = True

    @cached_property
    def config(self) -> Config:
        return load_config(self.deps.config_path)

    @cached_property
    def credentials(self) -> Credentials:
        return resolve_credentials(
            site_flag=self.site,
            profile_flag=self.profile,
            environ=self.deps.environ,
            config=self.config,
            secrets=self.deps.secrets,
        )

    @cached_property
    def client(self) -> Any:
        return self.deps.client_factory(
            self.credentials,
            sudo_as=self.sudo_as,
            trace_path=self.deps.environ.get(ENV_TRACE_FILE) or None,
        )

    def emit(self, data: Any) -> None:
        """Write a command result to stdout in the selected format."""
        fmt = resolve_format(self.fmt, is_tty=sys.stdout.isatty())
        render(data, fmt, sys.stdout, color=self.color)

    def note(self, message: str) -> None:
        """Write a human-facing remark to stderr."""
        print(message, file=sys.stderr)
