import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from fpt.cli import main
from fpt.client import Credentials, TracedClient
from fpt.context import Deps
from fpt.secrets import MemoryStore


class FakeClient:
    """Records every method call; returns canned responses or raises canned errors."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.responses: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def method(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            if name in self.errors:
                raise self.errors[name]
            return self.responses.get(name)

        return method


@dataclass(frozen=True)
class Result:
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    @property
    def error(self) -> dict[str, Any]:
        return json.loads(self.stderr)["error"]


class Harness:
    def __init__(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.client = FakeClient()
        self.secrets = MemoryStore()
        self.env: dict[str, str] = {}
        self.config_path = tmp_path / "config.toml"
        self.built: list[tuple[Credentials, str | None]] = []
        self._capsys = capsys
        self._monkeypatch = monkeypatch

    def _factory(
        self, credentials: Credentials, *, sudo_as: str | None = None, trace_path: str | None = None
    ) -> TracedClient:
        self.built.append((credentials, sudo_as))
        return TracedClient(self.client, trace_path)

    def use_script_env(self) -> None:
        self.env.update(
            FPT_SITE="https://env.example.com", FPT_SCRIPT_NAME="envbot", FPT_API_KEY="env-key"
        )

    def run(self, *args: str, stdin: str = "") -> Result:
        self._monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        deps = Deps(
            environ=self.env,
            config_path=self.config_path,
            secrets=self.secrets,
            client_factory=self._factory,
        )
        code = main(list(args), deps=deps)
        captured = self._capsys.readouterr()
        return Result(code, captured.out, captured.err)


@pytest.fixture
def harness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> Harness:
    return Harness(tmp_path, capsys, monkeypatch)
