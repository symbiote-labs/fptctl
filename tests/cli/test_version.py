import pytest

from fptctl import __version__
from fptctl.cli import main


def test_version_prints_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"])
    assert code == 0
    assert capsys.readouterr().out.strip() == f"fptctl, version {__version__}"
