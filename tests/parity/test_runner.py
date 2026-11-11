import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import shotgun_api3
from parity.runner import (
    CASES_DIR,
    REDACTED,
    CliResult,
    Credentials,
    cli_env,
    decode,
    expected_args,
    load_cases,
    resolve,
    run_case,
)

CONTEXT = {
    "project": {"type": "Project", "id": 70, "name": "fpt_parity_x"},
    "user": None,
    "secrets": {"login": "ada", "password": "pw"},
}
CREDS = Credentials(site="https://x.example.com", script_name="bot", api_key="k")
SCHEMA = {"Project": {"name": "text"}}
DIMENSIONS: dict[str, Any] = {
    "surfaces": {"info": "info"},
    "not_exposed": {},
    "filter_operators": {},
    "enums": {},
    "enum_params": {},
}


class Lib:
    def __init__(self, base_url: str, api_key: str | None = None, connect: bool = True) -> None: ...

    def info(self) -> Any:
        return {"version": [8, 91, 0]}

    def preferences_read(self, prefs: Any = None) -> Any:
        return {"a": prefs}

    def schema(self, entity_type: str) -> Any:
        raise shotgun_api3.ShotgunError("Deprecated: use schema_field_read")

    def authenticate_human_user(
        self, user_login: str, user_password: str, auth_token: str | None = None
    ) -> Any:
        return {"type": "HumanUser", "id": 5}

    def upload_thumbnail(self, entity_type: str, entity_id: int, path: str, **kwargs: Any) -> Any:
        return 1


def test_resolve_exact_and_embedded_placeholders() -> None:
    assert resolve("${project}", CONTEXT) == CONTEXT["project"]
    assert resolve("${project.id}", CONTEXT) == 70
    assert resolve("/Project/${project.id}", CONTEXT) == "/Project/70"
    assert resolve('{"p": ${project}}', CONTEXT) == (
        '{"p": {"type":"Project","id":70,"name":"fpt_parity_x"}}'
    )
    assert resolve({"a": ["${secrets.login}"]}, CONTEXT) == {"a": ["ada"]}


@pytest.mark.parametrize("text", ["${nope}", "${project.nope}", "${user.id}"])
def test_unknown_or_missing_placeholders_raise(text: str) -> None:
    with pytest.raises(LookupError):
        resolve(text, CONTEXT)


def test_decode_turns_typed_input_into_datetimes() -> None:
    assert decode({"at": [{"$datetime": "2026-11-10T14:30:00Z"}]}) == {
        "at": [datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)]
    }
    assert decode({"$datetime": "x", "y": 1}) == {"$datetime": "x", "y": 1}


def test_expected_args_follow_the_trace_contract() -> None:
    lib = Lib("https://x")
    assert expected_args(
        lib.authenticate_human_user, {"user_login": "ada", "user_password": "pw"}
    ) == {
        "user_login": "ada",
        "user_password": REDACTED,
        "auth_token": None,
    }
    assert expected_args(
        lib.upload_thumbnail,
        {"entity_type": "Shot", "entity_id": 1, "path": "/a.png", "tag_list": "x"},
    ) == {"entity_type": "Shot", "entity_id": 1, "path": "/a.png", "tag_list": "x"}


def write_cases(tmp_path: Path, cases: list[dict[str, Any]]) -> Path:
    (tmp_path / "cases.json").write_text(json.dumps(cases))
    return tmp_path


GOOD = {"id": "a", "method": "info", "mode": "identical", "args": {}, "argv": ["info"]}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"extra": 1}, "unknown keys"),
        ({"mode": "fuzzy"}, "mode"),
        ({"masks": ["name"]}, "allowlist"),
        ({"method": "frobnicate"}, "frobnicate"),
        ({"argv": "info"}, "argv"),
        ({"auth": "token"}, "auth"),
        ({"env": ["FPTCTL_CA_CERTS"]}, "env"),
        ({"env": {"FPTCTL_CA_CERTS": 1}}, "env"),
    ],
)
def test_case_validation(tmp_path: Path, change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_cases(write_cases(tmp_path, [{**GOOD, **change}]), {"info"})


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(write_cases(tmp_path, [GOOD, GOOD]), {"info"})


def test_real_case_files_load() -> None:
    names = {name for name in dir(shotgun_api3.Shotgun) if not name.startswith("_")}
    assert load_cases(CASES_DIR, names)


def test_cli_env_drops_inherited_fpt_variables(tmp_path: Path) -> None:
    env = cli_env(
        {"PATH": "/bin", "FPTCTL_PROFILE": "studio", "FPT_TEST_API_KEY": "k"},
        CREDS,
        "script",
        trace_path=tmp_path / "t.jsonl",
        config_path=tmp_path / "missing.toml",
    )
    assert env["PATH"] == "/bin" and "FPTCTL_PROFILE" not in env and "FPT_TEST_API_KEY" not in env
    assert (env["FPTCTL_SITE"], env["FPTCTL_SCRIPT_NAME"], env["FPTCTL_API_KEY"]) == (
        "https://x.example.com",
        "bot",
        "k",
    )
    assert env["FPTCTL_CONFIG"].endswith("missing.toml") and env["NO_COLOR"] == "1"
    user = cli_env(
        {},
        Credentials("https://x", "bot", "k", login="ada", password="pw"),
        "user",
        trace_path=tmp_path / "t",
        config_path=tmp_path / "c",
    )
    assert (user["FPTCTL_LOGIN"], user["FPTCTL_PASSWORD"]) == ("ada", "pw")
    assert "FPTCTL_API_KEY" not in user


def fake_cli(
    stdout: Any, trace_args: dict[str, Any], method: str = "info", code: int = 0, stderr: str = ""
) -> Any:
    def run(argv: list[str], stdin: str | None, auth: str, env: Any = None) -> CliResult:
        body = stdout if isinstance(stdout, bytes) else json.dumps(stdout).encode()
        trace = [
            {"construct": {"base_url": "https://x", "api_key": REDACTED, "connect": False}},
            {"call": method, "args": trace_args},
        ]
        return CliResult(code, body, stderr, trace)

    return run


def run(case: dict[str, Any], cli: Any) -> dict[str, Any]:
    return run_case(
        case,
        clients={"script": Lib("https://x")},
        contexts={"direct": CONTEXT, "cli": CONTEXT},
        run_cli=cli,
        schema_fields=SCHEMA,
        dimensions=DIMENSIONS,
        cls=Lib,
        created=[],
    )


def test_run_case_identical_pass_and_coverage() -> None:
    record = run(GOOD, fake_cli({"version": [8, 91, 0]}, {}))
    assert record["status"] == "pass", record["problems"]
    assert {"method:info", "param:Shotgun.base_url", "param:Shotgun.connect"} <= set(
        record["covers"]
    )


def test_run_case_reports_a_response_difference() -> None:
    record = run(GOOD, fake_cli({"version": [8, 90, 0]}, {}))
    assert record["status"] == "failing"
    assert any("version" in problem for problem in record["problems"])


def test_run_case_error_mode() -> None:
    case = {
        "id": "s",
        "method": "schema",
        "mode": "error",
        "args": {"entity_type": "Shot"},
        "argv": ["api", "call", "schema", "--args", '{"entity_type": "Shot"}'],
    }
    stderr = json.dumps(
        {
            "error": {
                "type": "api_fault",
                "details": {},
                "message": "Deprecated: use schema_field_read",
            }
        }
    )
    record = run(case, fake_cli(b"", {"entity_type": "Shot"}, "schema", code=5, stderr=stderr))
    assert record["status"] == "pass", record["problems"]
    assert "method:schema" in record["covers"]


def test_run_case_with_a_missing_fixture_is_blocked() -> None:
    case = {
        **GOOD,
        "id": "u",
        "method": "preferences_read",
        "args": {"prefs": "${user.id}"},
        "argv": ["api", "call", "preferences_read"],
    }
    record = run(case, fake_cli({}, {}))
    assert record["status"] == "blocked"
    assert record["covers"] == []


def test_run_case_records_the_unresolved_argv() -> None:
    case = {
        **GOOD,
        "id": "p",
        "method": "preferences_read",
        "args": {"prefs": ["${secrets.login}"]},
        "argv": ["api", "call", "preferences_read", "--args", '{"prefs": ["${secrets.login}"]}'],
    }
    record = run(case, fake_cli({"a": ["ada"]}, {"prefs": ["ada"]}, "preferences_read"))
    assert record["status"] == "pass", record["problems"]
    assert record["argv"] == case["argv"]


def test_run_case_passes_every_argv_item_as_text() -> None:
    seen: list[list[str]] = []
    respond = fake_cli({"version": [8, 91, 0]}, {})

    def cli(argv: list[str], stdin: str | None, auth: str, env: Any) -> CliResult:
        seen.append(argv)
        return respond(argv, stdin, auth, env)

    case = {**GOOD, "argv": ["info", "${project.id}", "${project}", "x${project.id}"]}
    run(case, cli)
    assert seen == [["info", "70", '{"type":"Project","id":70,"name":"fpt_parity_x"}', "x70"]]


def test_session_and_env_cases_load(tmp_path: Path) -> None:
    case = {**GOOD, "auth": "session", "env": {"FPTCTL_CA_CERTS": "${ca_certs}"}}
    assert load_cases(write_cases(tmp_path, [case]), {"info"}) == [case]


def test_cli_env_session_auth_and_extra_variables(tmp_path: Path) -> None:
    creds = Credentials("https://x", "bot", "k", session_token="tok")
    env = cli_env(
        {},
        creds,
        "session",
        trace_path=tmp_path / "t",
        config_path=tmp_path / "c",
        extra={"FPTCTL_CA_CERTS": "/certs.pem"},
    )
    assert env["FPTCTL_SESSION_TOKEN"] == "tok"
    assert env["FPTCTL_CA_CERTS"] == "/certs.pem"
    assert not {"FPTCTL_SCRIPT_NAME", "FPTCTL_API_KEY", "FPTCTL_LOGIN", "FPTCTL_PASSWORD"} & set(
        env
    )


def test_run_case_resolves_env_and_uses_the_session_client() -> None:
    seen: list[tuple[str, Any]] = []
    respond = fake_cli({"version": [8, 91, 0]}, {})

    def cli(argv: list[str], stdin: str | None, auth: str, env: Any) -> CliResult:
        seen.append((auth, env))
        return respond(argv, stdin, auth, env)

    case = {**GOOD, "auth": "session", "env": {"FPTCTL_CA_CERTS": "${ca_certs}"}}
    context = {**CONTEXT, "ca_certs": "/certs.pem"}
    record = run_case(
        case,
        clients={"script": Lib("https://x"), "session": Lib("https://x")},
        contexts={"direct": context, "cli": context},
        run_cli=cli,
        schema_fields=SCHEMA,
        dimensions=DIMENSIONS,
        cls=Lib,
        created=[],
    )
    assert record["status"] == "pass", record["problems"]
    assert seen == [("session", {"FPTCTL_CA_CERTS": "/certs.pem"})]
    blocked = run(case, cli)
    assert blocked["status"] == "blocked"
    assert blocked["problems"] == ["no session credentials in this run"]


@pytest.mark.parametrize(
    "change",
    [{"result_type": "Attachment"}, {"mode": "mirrored", "result_type": 1, "readback": {}}],
)
def test_result_type_is_only_for_mirrored_cases(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="result_type"):
        load_cases(write_cases(tmp_path, [{**GOOD, **change}]), {"info"})


class UploadLib(Lib):
    def __init__(self) -> None:
        self.read: list[Any] = []

    def upload(self, entity_type: str, entity_id: int, path: str) -> Any:
        return 941

    def find_one(self, entity_type: str, filters: Any, fields: Any) -> Any:
        self.read.append((entity_type, filters))
        return {"type": entity_type, "id": filters[0][2], "display_name": "x"}


def test_run_case_wraps_a_bare_id_result() -> None:
    lib = UploadLib()
    created: list[dict[str, Any]] = []
    args = {"entity_type": "Shot", "entity_id": 1, "path": "a.png"}
    case = {
        "id": "upload", "method": "upload", "mode": "mirrored", "args": args,
        "argv": ["upload", "Shot", "1", "a.png"], "masks": ["id"],
        "result_type": "Attachment",
        "readback": {"entity": "result", "fields": ["display_name"]},
    }  # fmt: skip
    record = run_case(
        case,
        clients={"script": lib},
        contexts={"direct": CONTEXT, "cli": CONTEXT},
        run_cli=fake_cli(942, args, method="upload"),
        schema_fields=SCHEMA,
        dimensions=DIMENSIONS,
        cls=Lib,
        created=created,
    )
    assert record["status"] == "pass", record["problems"]
    assert lib.read == [("Attachment", [["id", "is", 941]]), ("Attachment", [["id", "is", 942]])]
    assert created == [{"type": "Attachment", "id": 941}, {"type": "Attachment", "id": 942}]
