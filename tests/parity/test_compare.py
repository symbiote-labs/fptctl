import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from parity.compare import (
    MASK_ALLOWLIST,
    DirectError,
    Observation,
    apply_masks,
    as_entity,
    check_masks,
    diff,
    expected_exit_code,
    judge,
    wire,
)

ARGS = {"entity_type": "Shot", "filters": [], "fields": None}
ROWS = [{"type": "Shot", "id": 1, "code": "sh010"}]


def observe(**overrides: Any) -> Observation:
    base: dict[str, Any] = {
        "mode": "identical",
        "method": "find",
        "expected_args": ARGS,
        "trace": [{"construct": {}}, {"call": "find", "args": ARGS}],
        "exit_code": 0,
        "stdout": json.dumps(ROWS).encode(),
        "stderr": "",
        "direct": ROWS,
        "direct_again": ROWS,
    }
    return Observation(**{**base, **overrides})


def test_wire_matches_the_spec_table() -> None:
    plus5 = timezone(timedelta(hours=5))
    assert wire({"a": (1, datetime(2026, 11, 10, 14, 30, tzinfo=plus5))}) == {
        "a": [1, "2026-11-10T09:30:00Z"]
    }
    assert wire(datetime(2026, 11, 10, 9, 30)) == "2026-11-10T09:30:00"
    assert wire(date(2026, 11, 10)) == "2026-11-10"
    with pytest.raises(TypeError):
        wire(b"x")


def test_allowlist_is_exactly_the_spec_list() -> None:
    assert MASK_ALLOWLIST == {"id", "created_at", "updated_at"}
    with pytest.raises(ValueError, match="name"):
        check_masks(["id", "name"])


def test_masks_apply_at_every_depth() -> None:
    value = {"id": 1, "project": {"type": "Project", "id": 2, "name": "p"}, "links": [{"id": 3}]}
    assert apply_masks(value, frozenset({"id"})) == {
        "project": {"type": "Project", "name": "p"},
        "links": [{}],
    }


def test_diff_semantics() -> None:
    assert diff({"a": 1, "b": 2}, {"b": 2, "a": 1}) == []
    assert diff([1, 2], [2, 1]) != []
    assert diff(True, 1) != []
    assert diff(1, 1.0) == []
    assert diff({"a": 1}, {}) == ["$.a: missing from CLI output"]


@pytest.mark.parametrize(
    ("names", "code"),
    [
        (("MissingTwoFactorAuthenticationFault", "Fault", "ShotgunError", "Exception"), 3),
        (("AuthenticationFault", "Fault", "ShotgunError", "Exception"), 3),
        (("Fault", "ShotgunError", "Exception"), 5),
        (("ShotgunError", "Exception"), 5),
        (("ProtocolError", "Error", "Exception"), 6),
        (("SSLCertVerificationError", "SSLError", "OSError", "Exception"), 6),
        (("ValueError", "Exception"), 2),
        (("RuntimeError", "Exception"), 1),
    ],
)
def test_expected_exit_code(names: tuple[str, ...], code: int) -> None:
    assert expected_exit_code(names) == code


def test_identical_pass() -> None:
    assert judge(observe()).status == "pass"


def test_identical_unstable_when_direct_calls_differ() -> None:
    assert judge(observe(direct_again=[])).status == "unstable"


@pytest.mark.parametrize(
    "overrides",
    [
        {"stdout": b"[]"},
        {"stdout": b"not json"},
        {"exit_code": 5},
        {"stderr": "warning"},
        {"direct": [], "direct_again": []},
        {"trace": [{"call": "find", "args": {**ARGS, "fields": ["code"]}}]},
        {"trace": [{"call": "find", "args": ARGS}, {"call": "find", "args": ARGS}]},
        {"trace": [{"call": "find_one", "args": ARGS}]},
        {"trace": []},
    ],
)
def test_identical_failures(overrides: dict[str, Any]) -> None:
    outcome = judge(observe(**overrides))
    assert outcome.status == "failing"
    assert outcome.problems


def test_direct_error_outside_error_mode_is_blocked() -> None:
    outcome = judge(observe(direct_error=DirectError(("Fault", "Exception"), "nope")))
    assert outcome.status == "blocked"


def test_mirrored_compares_results_and_readbacks_under_masks() -> None:
    a = {"type": "Shot", "id": 10, "code": "twin", "project": {"type": "Project", "id": 1}}
    b = {**a, "id": 11}
    ok = observe(
        mode="mirrored",
        masks=frozenset({"id"}),
        direct=a,
        stdout=json.dumps(b).encode(),
        direct_readback=a,
        cli_readback=b,
    )
    assert judge(ok).status == "pass"
    bad = observe(
        mode="mirrored",
        masks=frozenset({"id"}),
        direct=a,
        stdout=json.dumps(b).encode(),
        direct_readback=a,
        cli_readback={**b, "code": "x"},
    )
    assert judge(bad).status == "failing"


def test_bytes_mode_compares_hashes() -> None:
    assert judge(observe(mode="bytes", direct=b"abc", stdout=b"abc")).status == "pass"
    outcome = judge(observe(mode="bytes", direct=b"abc", stdout=b"abd"))
    assert outcome.status == "failing"
    assert hashlib.sha256(b"abc").hexdigest() in " ".join(outcome.problems)


def test_error_mode() -> None:
    error = DirectError(("ShotgunError", "Exception"), "schema is deprecated")
    stderr = json.dumps(
        {"error": {"type": "api_fault", "message": "schema is deprecated", "details": {}}}
    )
    passing = observe(mode="error", direct_error=error, exit_code=5, stdout=b"", stderr=stderr)
    assert judge(passing).status == "pass"
    assert (
        judge(
            observe(mode="error", direct_error=error, exit_code=1, stdout=b"", stderr=stderr)
        ).status
        == "failing"
    )
    assert judge(observe(mode="error", exit_code=5, stdout=b"", stderr=stderr)).status == "failing"


def test_mirrored_bare_id_results_compare_as_entities() -> None:
    upload = {
        "mode": "mirrored",
        "method": "upload",
        "trace": [{"call": "upload", "args": ARGS}],
        "direct": 941,
        "stdout": b"942",
        "direct_readback": {"type": "Attachment", "id": 941, "display_name": "x"},
        "cli_readback": {"type": "Attachment", "id": 942, "display_name": "x"},
        "result_type": "Attachment",
    }
    assert judge(observe(**upload, masks=frozenset({"id"}))).status == "pass"
    assert judge(observe(**upload)).status == "failing"
    assert judge(observe(**{**upload, "result_type": None}, masks=frozenset({"id"}))).status == (
        "failing"
    )


def test_result_type_leaves_non_int_results_alone() -> None:
    assert as_entity("sg_x", "Attachment") == "sg_x"
    assert as_entity(True, "Attachment") is True
    assert as_entity(941, "Attachment") == {"type": "Attachment", "id": 941}
    assert as_entity(941, None) == 941
    outcome = judge(
        observe(
            mode="mirrored",
            masks=frozenset({"id"}),
            direct=941,
            stdout=b'"941"',
            result_type="Attachment",
        )
    )
    assert outcome.status == "failing"
