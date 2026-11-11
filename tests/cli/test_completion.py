import pytest

from fptctl.cli import main


def test_bash_completion_script(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("_FPTCTL_COMPLETE", "bash_source")
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 0
    assert "_fptctl_completion" in capsys.readouterr().out


def test_bash_completion_offers_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("_FPTCTL_COMPLETE", "bash_complete")
    monkeypatch.setenv("COMP_WORDS", "fptctl sch")
    monkeypatch.setenv("COMP_CWORD", "1")
    with pytest.raises(SystemExit):
        main([])
    assert "plain,schema" in capsys.readouterr().out.splitlines()
