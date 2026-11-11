from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def test_methods_lists_signatures_without_credentials(harness: Any) -> None:
    result = harness.run("api", "methods")
    assert result.code == 0
    by_name = {row["name"]: row["signature"] for row in result.json}
    assert "entity_type" in by_name["find"]
    assert "self" not in by_name["find"]
    assert {"nav_expand", "preferences_read", "schema"} <= set(by_name)
    assert "server_info" not in by_name
    assert harness.built == []


def test_call_passes_keyword_arguments(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["find"] = [{"type": "Shot", "id": 1}]
    result = harness.run(
        "api", "call", "find", "--args", '{"entity_type": "Shot", "filters": [], "limit": 2}'
    )
    assert result.code == 0
    assert result.json == [{"type": "Shot", "id": 1}]
    assert harness.client.calls == [
        ("find", (), {"entity_type": "Shot", "filters": [], "limit": 2})
    ]


def test_call_without_args_sends_none(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["preferences_read"] = {"format_date_fields": "US"}
    assert harness.run("api", "call", "preferences_read").json == {"format_date_fields": "US"}
    assert harness.client.calls == [("preferences_read", (), {})]


def test_call_decodes_datetimes_and_encodes_results(harness: Any) -> None:
    harness.use_script_env()
    when = datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)
    harness.client.responses["work_schedule_read"] = {"at": when}
    args = '{"start_date": "2026-11-10", "end_date": {"$datetime": "2026-11-10T14:30:00Z"}}'
    result = harness.run("api", "call", "work_schedule_read", "--args", args)
    assert result.json == {"at": "2026-11-10T14:30:00Z"}
    assert harness.client.calls[0][2]["end_date"] == when


def test_call_reads_args_from_stdin_and_file(harness: Any, tmp_path: Path) -> None:
    harness.use_script_env()
    harness.run(
        "api",
        "call",
        "authenticate_human_user",
        "--args",
        "-",
        stdin='{"user_login": "ada", "user_password": "pw"}',
    )
    path = tmp_path / "args.json"
    path.write_text('{"prefs": ["x"]}')
    harness.run("api", "call", "preferences_read", "--args", f"@{path}")
    assert [call[2] for call in harness.client.calls] == [
        {"user_login": "ada", "user_password": "pw"},
        {"prefs": ["x"]},
    ]


def test_unknown_method_is_a_usage_error_before_connecting(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("api", "call", "frobnicate")
    assert result.code == 2
    assert "fptctl api methods" in result.error["message"]
    assert harness.built == []


def test_args_must_be_an_object(harness: Any) -> None:
    harness.use_script_env()
    assert harness.run("api", "call", "info", "--args", "[1]").code == 2
    assert harness.run("api", "call", "info", "--args", "{nope").code == 2


def test_none_prints_null(harness: Any) -> None:
    harness.use_script_env()
    result = harness.run("api", "call", "close")
    assert (result.code, result.stdout) == (0, "null\n")


def test_bytes_result_exits_1(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["download_attachment"] = b"\x89PNG"
    result = harness.run(
        "api", "call", "download_attachment", "--args", '{"attachment": {"id": 1}}'
    )
    assert result.code == 1
    assert result.stdout == ""
