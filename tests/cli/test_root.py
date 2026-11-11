import json
from typing import Any

import shotgun_api3

INFO = {"version": [8, 60, 0], "s3_uploads_enabled": True}


def test_info_prints_server_info_as_json(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["info"] = INFO
    result = harness.run("info")
    assert result.code == 0
    assert result.json == INFO
    assert result.stderr == ""
    assert harness.client.calls == [("info", (), {})]


def test_client_is_built_from_resolved_credentials(harness: Any) -> None:
    harness.use_script_env()
    harness.run("--sudo-as", "ada", "info")
    credentials, sudo_as = harness.built[0]
    assert credentials.site == "https://env.example.com"
    assert credentials.script_name == "envbot"
    assert sudo_as == "ada"


def test_format_option_changes_output(harness: Any) -> None:
    harness.use_script_env()
    harness.client.responses["info"] = INFO
    result = harness.run("--format", "ndjson", "info")
    assert result.stdout == json.dumps(INFO) + "\n"


def test_site_flag_overrides_env_site(harness: Any) -> None:
    harness.use_script_env()
    harness.run("--site", "other.example.com", "info")
    assert harness.built[0][0].site == "https://other.example.com"


def test_missing_credentials_exit_3_with_structured_error(harness: Any) -> None:
    result = harness.run("info")
    assert result.code == 3
    assert result.stdout == ""
    assert result.error["type"] == "auth"
    assert "fpt auth login" in result.error["message"]
    assert harness.built == []


def test_api_fault_exits_5(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["info"] = shotgun_api3.Fault("API read() invalid")
    result = harness.run("info")
    assert result.code == 5
    assert result.error == {
        "type": "api_fault",
        "message": "API read() invalid",
        "details": {"exception": "Fault"},
    }


def test_authentication_fault_exits_3(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["info"] = shotgun_api3.AuthenticationFault("Can't authenticate script")
    assert harness.run("info").code == 3


def test_connection_failure_exits_6(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["info"] = ConnectionRefusedError("refused")
    result = harness.run("info")
    assert result.code == 6
    assert result.error["type"] == "network"


def test_unexpected_exception_exits_1(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["info"] = RuntimeError("surprise")
    result = harness.run("info")
    assert result.code == 1
    assert result.error["type"] == "unexpected"


def test_unknown_command_exits_2(harness: Any) -> None:
    result = harness.run("frobnicate")
    assert result.code == 2
    assert result.error["type"] == "usage"
    assert "frobnicate" in result.error["message"]


def test_bad_format_value_exits_2(harness: Any) -> None:
    assert harness.run("--format", "yaml", "info").code == 2


def test_no_arguments_prints_help_and_exits_0(harness: Any) -> None:
    result = harness.run()
    assert result.code == 0
    assert "Usage: fpt" in result.stdout
    assert "info" in result.stdout


def test_help_does_not_need_credentials(harness: Any) -> None:
    result = harness.run("info", "--help")
    assert result.code == 0
    assert harness.built == []


def test_trace_file_records_the_library_call(harness: Any, tmp_path: Any) -> None:
    harness.use_script_env()
    trace = tmp_path / "trace.jsonl"
    harness.env["FPT_TRACE_FILE"] = str(trace)
    harness.client.responses["info"] = INFO
    assert harness.run("info").code == 0
    assert [json.loads(line)["call"] for line in trace.read_text().splitlines()] == ["info"]


def test_library_value_error_exits_2(harness: Any) -> None:
    harness.use_script_env()
    harness.client.errors["info"] = ValueError("bad argument")
    result = harness.run("info")
    assert result.code == 2
    assert result.error == {
        "type": "usage",
        "message": "bad argument",
        "details": {"exception": "ValueError"},
    }
