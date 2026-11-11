import pytest

from fpt import __version__
from fpt.cli import main


def test_version_prints_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--version"])
    assert code == 0
    assert capsys.readouterr().out.strip() == f"fpt, version {__version__}"
