import json
import os
from pathlib import Path

import pytest

from fpt.cli import main
from fpt.client import build_client
from fpt.context import Deps
from fpt.secrets import MemoryStore

pytestmark = pytest.mark.live

REQUIRED = ("FPT_TEST_SITE", "FPT_TEST_SCRIPT_NAME", "FPT_TEST_API_KEY")


def make_deps(tmp_path: Path, **overrides: str) -> Deps:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip(f"live tests need {', '.join(missing)}")
    environ = {
        "FPT_SITE": os.environ["FPT_TEST_SITE"],
        "FPT_SCRIPT_NAME": os.environ["FPT_TEST_SCRIPT_NAME"],
        "FPT_API_KEY": os.environ["FPT_TEST_API_KEY"],
        **overrides,
    }
    return Deps(
        environ=environ,
        config_path=tmp_path / "config.toml",
        secrets=MemoryStore(),
        client_factory=build_client,
    )


def test_info_returns_a_server_version(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info"], deps=make_deps(tmp_path)) == 0
    assert "version" in json.loads(capsys.readouterr().out)


def test_auth_status_succeeds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["auth", "status"], deps=make_deps(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_wrong_api_key_exits_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    deps = make_deps(tmp_path, FPT_API_KEY="definitely-not-the-key")
    assert main(["auth", "status"], deps=deps) == 3
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "auth"


def test_unreachable_site_exits_6(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    deps = make_deps(tmp_path, FPT_SITE="https://fpt-no-such-host.invalid")
    assert main(["auth", "status"], deps=deps) == 6
    assert json.loads(capsys.readouterr().err)["error"]["type"] == "network"
