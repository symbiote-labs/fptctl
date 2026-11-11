from typing import Any

import pytest

USER = {"type": "HumanUser", "id": 5}
SHOT = {"type": "Shot", "id": 12}
PROJECT = {"type": "Project", "id": 70}


def sent(harness: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(name, kwargs) for name, _, kwargs in harness.client.calls]


@pytest.mark.parametrize("method", ["follow", "unfollow"])
def test_follow_and_unfollow(harness: Any, method: str) -> None:
    harness.use_script_env()
    harness.client.responses[method] = {"followed": True, "user": USER, "entity": SHOT}
    result = harness.run(method, "HumanUser:5", "Shot:12")
    assert (result.code, result.json) == (0, {"followed": True, "user": USER, "entity": SHOT})
    harness.run(method, '{"type": "HumanUser", "id": 5}', '{"type": "Shot", "id": 12}')
    assert sent(harness) == [(method, {"user": USER, "entity": SHOT})] * 2


def test_followers(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["followers"] = [USER]
    result = harness.run("followers", "Shot:12")
    assert (result.code, result.json) == (0, [USER])
    assert sent(harness) == [("followers", {"entity": SHOT})]


def test_following(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["following"] = [SHOT]
    result = harness.run("following", "HumanUser:5")
    assert (result.code, result.json) == (0, [SHOT])
    harness.run("following", "HumanUser:5", "--project", "Project:70", "--entity-type", "Shot")
    assert sent(harness) == [
        ("following", {"user": USER}),
        ("following", {"user": USER, "project": PROJECT, "entity_type": "Shot"}),
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["follow", "5", "Shot:12"],
        ["follow", "HumanUser:5", "x"],
        ["follow", "HumanUser:5"],
        ["unfollow", "HumanUser:5", "[1]"],
        ["followers", "12"],
        ["following", "x"],
        ["following", "HumanUser:5", "--project", "70"],
    ],
)
def test_social_usage_errors(harness: Any, argv: list[str]) -> None:
    harness.use_script_env()
    assert harness.run(*argv).code == 2
    assert harness.client.calls == []


@pytest.mark.parametrize("method", ["follow", "unfollow"])
def test_follow_dry_run(harness: Any, method: str) -> None:
    result = harness.run(method, "HumanUser:5", "Shot:12", "--dry-run")
    assert (result.code, result.json) == (
        0,
        {"call": method, "args": {"user": USER, "entity": SHOT}},
    )
    assert harness.built == []
