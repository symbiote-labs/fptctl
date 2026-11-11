import io
import json

import pytest

from fptctl.errors import (
    ApiFaultError,
    AuthError,
    ExitCode,
    FptError,
    NetworkError,
    NotFoundError,
    UsageError,
    emit_error,
    error_payload,
)


@pytest.mark.parametrize(
    ("cls", "code", "error_type"),
    [
        (FptError, 1, "unexpected"),
        (UsageError, 2, "usage"),
        (AuthError, 3, "auth"),
        (NotFoundError, 4, "not_found"),
        (ApiFaultError, 5, "api_fault"),
        (NetworkError, 6, "network"),
    ],
)
def test_each_error_has_its_exit_code_and_type(
    cls: type[FptError], code: int, error_type: str
) -> None:
    err = cls("boom")
    assert int(err.exit_code) == code
    assert err.error_type == error_type
    assert str(err) == "boom"


def test_exit_code_ok_is_zero() -> None:
    assert int(ExitCode.OK) == 0


def test_error_payload_shape() -> None:
    err = NotFoundError("Shot 5 not found", {"type": "Shot", "id": 5})
    assert error_payload(err) == {
        "error": {
            "type": "not_found",
            "message": "Shot 5 not found",
            "details": {"type": "Shot", "id": 5},
        }
    }


def test_emit_error_writes_one_json_line_when_not_a_tty() -> None:
    stream = io.StringIO()
    emit_error(AuthError("bad key"), stream, is_tty=False)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"error": {"type": "auth", "message": "bad key", "details": {}}}


def test_emit_error_writes_plain_text_on_a_tty() -> None:
    stream = io.StringIO()
    emit_error(AuthError("bad key"), stream, is_tty=True)
    assert stream.getvalue() == "error: bad key\n"
