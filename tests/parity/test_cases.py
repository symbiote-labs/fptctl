"""Every committed case through fpt with a fake client: the command line makes its call."""

import functools
from datetime import date
from typing import Any

import pytest
import shotgun_api3
from parity.runner import CASES_DIR, _as_text, decode, expected_args, load_cases, resolve

from parity import fixtures

CONTEXT = {
    "project": {"type": "Project", "id": 70, "name": "fpt_parity_RUN"},
    "twin": {"type": "Shot", "id": 1, "name": "fpt_parity_twin"},
    "past": {"type": "Shot", "id": 2, "name": "fpt_parity_past"},
    "victim": {"type": "Shot", "id": 4, "name": "fpt_parity_victim"},
    "task": {"type": "Task", "id": 3, "name": "fpt_parity_task"},
    "user": {"type": "HumanUser", "id": 5, "name": "Ada"},
    "subscription": {"humanUserId": 5, "subscription": "x"},
    "dates": fixtures.run_dates(date(2026, 11, 10)),
    "secrets": {"login": "ada", "password": "pw"},
    "attachment": {"type": "Attachment", "id": 6},
    "note": {"type": "Note", "id": 7},
    "activity": {"min_id": 900, "max_id": 902},
    "run_id": "RUN",
    "scratch": {
        "entity_type": "Asset",
        "display_name": "fpt parity scratch RUN",
        "field": "sg_fpt_parity_scratch_run",
    },
}
CASES = load_cases(CASES_DIR, {name for name in dir(shotgun_api3.Shotgun) if name[0] != "_"})


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_the_command_line_makes_the_cases_call(harness: Any, case: dict[str, Any]) -> None:
    harness.use_script_env()
    # Each argv item as text: what a command line receives.
    argv = [
        item if isinstance(item, str) else _as_text(item)
        for item in resolve([*case.get("global_args", []), *case["argv"]], CONTEXT)
    ]
    stdin = resolve(case["stdin"], CONTEXT) if "stdin" in case else ""
    result = harness.run(*argv, stdin=stdin)
    assert result.code == 0, result.stderr
    [(method, args, kwargs)] = harness.client.calls
    assert (method, args) == (case["method"], ())
    function = functools.partial(getattr(shotgun_api3.Shotgun, method), None)
    assert expected_args(function, kwargs) == expected_args(
        function, decode(resolve(case["args"], CONTEXT))
    )
