import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import shotgun_api3

from fptctl.client import (
    REDACTED,
    Credentials,
    TracedClient,
    bind_arguments,
    build_client,
    describe_call,
    redact,
)
from fptctl.errors import UsageError


class Library:
    version = "3.10.5"

    def find(self, entity_type: str, filters: list[Any], fields: Any = None, limit: int = 0) -> Any:
        return [{"type": entity_type, "id": 1}]

    def upload_thumbnail(self, entity_type: str, entity_id: int, path: str, **kwargs: Any) -> int:
        return 9

    def strict(self, value: int) -> None:
        raise ValueError("value must be positive")


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_bind_arguments_fills_defaults_and_flattens_kwargs() -> None:
    lib = Library()
    assert bind_arguments(lib.find, ("Shot", []), {"limit": 5}) == {
        "entity_type": "Shot",
        "filters": [],
        "fields": None,
        "limit": 5,
    }
    assert bind_arguments(lib.upload_thumbnail, ("Shot", 1, "/a.png"), {"tag_list": "x"}) == {
        "entity_type": "Shot",
        "entity_id": 1,
        "path": "/a.png",
        "tag_list": "x",
    }


def test_redact_hides_secrets_but_not_absent_ones() -> None:
    assert redact({"api_key": "k", "password": None, "login": "ada"}) == {
        "api_key": REDACTED,
        "password": None,
        "login": "ada",
    }


@pytest.mark.parametrize(
    ("proxy", "traced"),
    [
        ("ada:secret@proxy.example.com:8080", f"{REDACTED}@proxy.example.com:8080"),
        ("ada:p@ss@proxy.example.com", f"{REDACTED}@proxy.example.com"),
        ("proxy.example.com:8080", "proxy.example.com:8080"),
        (None, None),
    ],
    ids=["user-and-password", "at-sign-in-password", "no-credentials", "no-proxy"],
)
def test_redact_hides_proxy_credentials_but_keeps_the_host(
    proxy: str | None, traced: str | None
) -> None:
    assert redact({"http_proxy": proxy}) == {"http_proxy": traced}, (
        "the proxy's user:pass must never reach the trace"
    )


def test_traced_call_writes_one_wire_line_and_returns_the_result(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    client = TracedClient(Library(), str(trace))
    when = datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert client.find("Shot", [["created_at", "greater_than", when]]) == [
        {"type": "Shot", "id": 1}
    ]
    assert lines(trace) == [
        {
            "call": "find",
            "args": {
                "entity_type": "Shot",
                "filters": [["created_at", "greater_than", "2026-11-10T00:00:00Z"]],
                "fields": None,
                "limit": 0,
            },
        }
    ]


def test_no_trace_file_writes_nothing(tmp_path: Path) -> None:
    TracedClient(Library()).find("Shot", [])
    assert list(tmp_path.iterdir()) == []


def test_attributes_pass_through() -> None:
    assert TracedClient(Library()).version == "3.10.5"


def test_bad_arguments_are_usage_errors_and_are_not_traced(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    with pytest.raises(UsageError, match="find"):
        TracedClient(Library(), str(trace)).find("Shot", [], nope=1)
    assert not trace.exists()


def test_value_error_from_the_library_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="positive") as caught:
        TracedClient(Library()).strict(-1)
    assert caught.value.details == {"exception": "ValueError"}


def test_build_client_traces_construction_with_secrets_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Recording:
        def __init__(
            self,
            base_url: str,
            script_name: str | None = None,
            api_key: str | None = None,
            http_proxy: str | None = None,
            ca_certs: str | None = None,
            sudo_as_login: str | None = None,
            connect: bool = True,
        ) -> None:
            pass

        def add_user_agent(self, agent: str) -> None:
            pass

    monkeypatch.setattr(shotgun_api3, "Shotgun", Recording)
    trace = tmp_path / "trace.jsonl"
    creds = Credentials(site="https://x.example.com", auth="script", secret="k", script_name="bot")
    build_client(creds, trace_path=str(trace))
    assert lines(trace) == [
        {
            "construct": {
                "base_url": "https://x.example.com",
                "script_name": "bot",
                "api_key": REDACTED,
                "http_proxy": None,
                "ca_certs": None,
                "sudo_as_login": None,
                "connect": False,
            }
        }
    ]


def test_describe_call_fills_defaults_like_the_trace() -> None:
    assert describe_call("update", {"entity_type": "Shot", "entity_id": 1, "data": {"a": 1}}) == {
        "call": "update",
        "args": {
            "entity_type": "Shot",
            "entity_id": 1,
            "data": {"a": 1},
            "multi_entity_update_modes": None,
        },
    }


def test_describe_call_redacts_secrets() -> None:
    record = describe_call("authenticate_human_user", {"user_login": "a", "user_password": "pw"})
    assert record["args"]["user_password"] == "<redacted>"
    assert record["args"]["user_login"] == "a"


def test_describe_call_rejects_unknown_arguments() -> None:
    with pytest.raises(UsageError, match="delete"):
        describe_call("delete", {"entity_type": "Shot", "entity_id": 1, "nope": 2})
