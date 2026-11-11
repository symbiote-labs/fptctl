"""Run every parity case against the sandbox: the library directly, then the fptctl binary.

`uv run python -m parity.runner`. Needs FPT_TEST_SITE, FPT_TEST_SCRIPT_NAME and FPT_TEST_API_KEY;
FPT_TEST_LOGIN and FPT_TEST_PASSWORD for cases with "auth": "user". Cases with "auth": "session"
give the CLI a session token from the script client's get_session_token(); their direct call uses
the script client. A case's "env" adds environment variables for the CLI side. A mirrored case's
"result_type" says its result is a bare id of that entity type (upload, thumbnails); it is compared
and read back as a link.

Changing this file needs the owner's approval once it is in use
(spec, "Rules for the executing agent").
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parity import burndown, fixtures
from parity.compare import (
    MODES,
    DirectError,
    Observation,
    as_entity,
    check_masks,
    judge,
    wire,
)
from parity.inventory import covered_items, load_dimensions

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = REPO_ROOT / "parity" / "cases"
RESULTS_DIR = REPO_ROOT / "parity" / "results"

# The trace contract with fptctl's client.py: these names are redacted to this value.
SECRET_ARGUMENTS = frozenset(
    {"api_key", "password", "session_token", "auth_token", "user_password"}
)
REDACTED = "<redacted>"

_REQUIRED_KEYS = {"id", "method", "mode", "args", "argv"}
_OPTIONAL_KEYS = {"global_args", "auth", "stdin", "masks", "readback", "env", "result_type"}
AUTH_MODES = ("script", "user", "session")
_PLACEHOLDER = re.compile(r"\$\{([a-z_]+(?:\.[a-z_]+)?)\}")
_CLI_TIMEOUT = 300


@dataclass(frozen=True)
class Credentials:
    site: str
    script_name: str
    api_key: str
    login: str | None = None
    password: str | None = None
    session_token: str | None = None


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: bytes
    stderr: str
    trace: list[dict[str, Any]]


RunCli = Callable[[list[str], "str | None", str, Mapping[str, str]], CliResult]


# --- case data -------------------------------------------------------------------------------


def _lookup(path: str, context: Mapping[str, Any]) -> Any:
    name, _, key = path.partition(".")
    if name not in context:
        raise LookupError(f"unknown placeholder ${{{path}}}")
    value = context[name]
    if key:
        if not isinstance(value, Mapping) or key not in value:
            raise LookupError(f"placeholder ${{{path}}} has no value in this run")
        value = value[key]
    if value is None:
        raise LookupError(f"placeholder ${{{path}}} has no value in this run")
    return value


def _as_text(value: Any) -> str:
    return (
        json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    )


def resolve(value: Any, context: Mapping[str, Any]) -> Any:
    """Replace ${name} and ${name.key} placeholders with fixture values."""
    if isinstance(value, str):
        exact = _PLACEHOLDER.fullmatch(value)
        if exact:
            return _lookup(exact.group(1), context)
        return _PLACEHOLDER.sub(lambda m: _as_text(_lookup(m.group(1), context)), value)
    if isinstance(value, list):
        return [resolve(item, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, context) for key, item in value.items()}
    return value


def decode(value: Any) -> Any:
    """Typed input (spec, "Wire format"): {"$datetime": "...Z"} becomes an aware datetime."""
    if isinstance(value, dict):
        if set(value) == {"$datetime"} and isinstance(value["$datetime"], str):
            text = value["$datetime"]
            if text.endswith("Z"):
                return datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(text)
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def load_cases(directory: Path, method_names: set[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            where = f"{path.name}: case {case.get('id')!r}"
            unknown = set(case) - _REQUIRED_KEYS - _OPTIONAL_KEYS
            missing = _REQUIRED_KEYS - set(case)
            if unknown or missing:
                raise ValueError(
                    f"{where}: unknown keys {sorted(unknown)}, missing {sorted(missing)}"
                )
            if case["mode"] not in MODES:
                raise ValueError(f"{where}: mode must be one of {', '.join(MODES)}")
            try:
                check_masks(case.get("masks", []))
            except ValueError as exc:
                raise ValueError(f"{where}: {exc}") from exc
            if case["method"] not in method_names:
                raise ValueError(f"{where}: {case['method']} is not a library method")
            for key in ("argv", "global_args"):
                if not isinstance(case.get(key, []), list):
                    raise ValueError(f"{where}: {key} must be a list of strings")
            if case.get("auth", "script") not in AUTH_MODES:
                raise ValueError(f"{where}: auth must be one of {', '.join(AUTH_MODES)}")
            env = case.get("env", {})
            if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
                raise ValueError(f"{where}: env must map variable names to strings")
            if "result_type" in case and (
                case["mode"] != "mirrored" or not isinstance(case["result_type"], str)
            ):
                raise ValueError(f"{where}: result_type must be a string, in a mirrored case")
            if case["mode"] == "mirrored" and "readback" not in case:
                raise ValueError(f"{where}: a mirrored case needs readback")
            if case["id"] in seen:
                raise ValueError(f"{where}: duplicate case id")
            seen.add(case["id"])
            cases.append(case)
    return cases


# --- the trace contract ----------------------------------------------------------------------


def _bind(func: Callable[..., Any], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    bound = signature.bind(**kwargs)
    bound.apply_defaults()
    arguments: dict[str, Any] = {}
    for name, value in bound.arguments.items():
        kind = signature.parameters[name].kind
        if kind is inspect.Parameter.VAR_KEYWORD:
            arguments.update(value)
        elif kind is inspect.Parameter.VAR_POSITIONAL:
            arguments[name] = list(value)
        else:
            arguments[name] = value
    return arguments


def expected_args(func: Callable[..., Any], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """What fptctl's trace must show for a call: bound, defaults filled, redacted, wire format."""
    bound = _bind(func, kwargs)
    redacted = {
        name: REDACTED if name in SECRET_ARGUMENTS and value is not None else value
        for name, value in bound.items()
    }
    result: dict[str, Any] = wire(redacted)
    return result


# --- running one case ------------------------------------------------------------------------


def _direct_error(exc: BaseException) -> DirectError:
    return DirectError(tuple(klass.__name__ for klass in type(exc).__mro__), str(exc))


def _record(
    case: Mapping[str, Any], status: str, problems: Sequence[str], covers: set[str]
) -> dict[str, Any]:
    return {
        "id": case["id"],
        "method": case["method"],
        "mode": case["mode"],
        "argv": [*case.get("global_args", []), *case["argv"]],
        "status": status,
        "problems": list(problems),
        "covers": sorted(covers),
        "masks": sorted(case.get("masks", [])),
    }


def _read_back(client: Any, target: Any, fields: list[str]) -> Any:
    if not isinstance(target, Mapping) or "type" not in target or "id" not in target:
        return None
    return wire(client.find_one(target["type"], [["id", "is", target["id"]]], fields))


def run_case(
    case: Mapping[str, Any],
    *,
    clients: Mapping[str, Any],
    contexts: Mapping[str, Mapping[str, Any]],
    run_cli: RunCli,
    schema_fields: Mapping[str, Mapping[str, str]],
    dimensions: Mapping[str, Any],
    cls: type,
    created: list[dict[str, Any]],
) -> dict[str, Any]:
    mode, method, auth = case["mode"], case["method"], case.get("auth", "script")
    client = clients.get(auth)
    if client is None:
        return _record(case, "blocked", [f"no {auth} credentials in this run"], set())
    cli_side = "cli" if mode == "mirrored" else "direct"
    try:
        direct_args = decode(resolve(case["args"], contexts["direct"]))
        cli_args = decode(resolve(case["args"], contexts[cli_side]))
        argv = [
            item if isinstance(item, str) else _as_text(item)
            for item in resolve([*case.get("global_args", []), *case["argv"]], contexts[cli_side])
        ]
        stdin = resolve(case["stdin"], contexts[cli_side]) if "stdin" in case else None
        env = {
            name: _as_text(value)
            for name, value in resolve(case.get("env", {}), contexts[cli_side]).items()
        }
    except LookupError as exc:
        return _record(case, "blocked", [str(exc)], set())
    function = getattr(client, method)
    observed: dict[str, Any] = {}
    problems: list[str] = []
    try:
        result = function(**direct_args)
    except Exception as exc:  # the direct call's failure is what an error case compares against
        observed["direct_error"] = _direct_error(exc)
    else:
        try:
            observed["direct"] = result if mode == "bytes" else wire(result)
        except TypeError as exc:
            problems.append(f"the direct result has no wire form, nothing to compare: {exc}")
    cli = run_cli(argv, stdin, auth, env)
    if mode == "identical" and "direct" in observed:
        try:
            observed["direct_again"] = wire(function(**direct_args))
        except Exception as exc:
            observed["direct_error"] = _direct_error(exc)
    if mode == "mirrored" and "direct" in observed:
        readback = case["readback"]
        fields = list(readback["fields"])
        try:
            cli_result = json.loads(cli.stdout)
        except ValueError:
            cli_result = None
        if readback["entity"] == "result":
            result_type = case.get("result_type")
            targets = {
                "direct": as_entity(observed["direct"], result_type),
                "cli": as_entity(cli_result, result_type),
            }
            created += [t for t in targets.values() if isinstance(t, dict) and "id" in t]
        else:
            targets = {
                side: resolve(readback["entity"], contexts[side]) for side in ("direct", "cli")
            }
        observed["direct_readback"] = _read_back(client, targets["direct"], fields)
        observed["cli_readback"] = _read_back(client, targets["cli"], fields)
    covers = covered_items(
        argv=case["argv"],
        trace=cli.trace,
        direct=observed.get("direct"),
        mode=mode,
        schema_fields=schema_fields,
        dimensions=dimensions,
        cls=cls,
    )
    if problems:
        return _record(case, "blocked", problems, covers)
    try:
        expected = expected_args(function, cli_args)
    except TypeError as exc:
        return _record(case, "blocked", [f"the case's args do not bind to {method}: {exc}"], covers)
    outcome = judge(
        Observation(
            mode=mode,
            method=method,
            expected_args=expected,
            trace=cli.trace,
            exit_code=cli.exit_code,
            stdout=cli.stdout,
            stderr=cli.stderr,
            masks=frozenset(case.get("masks", [])),
            result_type=case.get("result_type"),
            **observed,
        )
    )
    return _record(case, outcome.status, outcome.problems, covers)


# --- the CLI side ----------------------------------------------------------------------------


def cli_env(
    base: Mapping[str, str],
    creds: Credentials,
    auth: str,
    *,
    trace_path: Path,
    config_path: Path,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = {key: value for key, value in base.items() if not key.startswith(("FPT_", "FPTCTL_"))}
    env.update(
        FPTCTL_SITE=creds.site,
        FPTCTL_CONFIG=str(config_path),
        FPTCTL_TRACE_FILE=str(trace_path),
        NO_COLOR="1",
    )
    if auth == "user":
        env.update(FPTCTL_LOGIN=creds.login or "", FPTCTL_PASSWORD=creds.password or "")
    elif auth == "session":
        env.update(FPTCTL_SESSION_TOKEN=creds.session_token or "")
    else:
        env.update(FPTCTL_SCRIPT_NAME=creds.script_name, FPTCTL_API_KEY=creds.api_key)
    env.update(extra or {})
    return env


def subprocess_cli(creds: Credentials, workdir: Path) -> RunCli:
    def run(argv: list[str], stdin: str | None, auth: str, extra: Mapping[str, str]) -> CliResult:
        trace_path = workdir / "trace.jsonl"
        trace_path.unlink(missing_ok=True)
        env = cli_env(
            os.environ,
            creds,
            auth,
            trace_path=trace_path,
            config_path=workdir / "missing.toml",
            extra=extra,
        )
        done = subprocess.run(
            ["uv", "run", "--quiet", "fptctl", "--format", "json", *argv],
            cwd=REPO_ROOT,
            env=env,
            input=stdin.encode() if stdin is not None else b"",
            capture_output=True,
            timeout=_CLI_TIMEOUT,
        )
        trace = (
            [json.loads(line) for line in trace_path.read_text().splitlines()]
            if trace_path.exists()
            else []
        )
        return CliResult(done.returncode, done.stdout, done.stderr.decode(errors="replace"), trace)

    return run


# --- a whole run -----------------------------------------------------------------------------


def credentials_from_env(environ: Mapping[str, str]) -> tuple[Credentials | None, list[str]]:
    names = ("FPT_TEST_SITE", "FPT_TEST_SCRIPT_NAME", "FPT_TEST_API_KEY")
    missing = [name for name in names if not environ.get(name)]
    if missing:
        return None, missing
    creds = Credentials(
        site=environ["FPT_TEST_SITE"],
        script_name=environ["FPT_TEST_SCRIPT_NAME"],
        api_key=environ["FPT_TEST_API_KEY"],
        login=environ.get("FPT_TEST_LOGIN") or None,
        password=environ.get("FPT_TEST_PASSWORD") or None,
    )
    return creds, []


def snapshot_schema(sg: Any) -> dict[str, Any]:
    data_types: dict[str, bool] = {}
    fields: dict[str, dict[str, str]] = {}
    for entity_type, entity_fields in sg.schema_read().items():
        for name, field in entity_fields.items():
            data_type = field["data_type"]["value"]
            editable = bool(field["editable"]["value"])
            data_types[data_type] = data_types.get(data_type, False) or editable
            fields.setdefault(entity_type, {})[name] = data_type
    return {"data_types": data_types, "fields": fields}


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(prog="python -m parity.runner", description=__doc__).parse_args(argv)
    creds, missing = credentials_from_env(os.environ)
    if creds is None:
        print(f"parity.runner needs {', '.join(missing)}", file=sys.stderr)
        return 2
    import shotgun_api3

    cls = shotgun_api3.Shotgun
    dimensions = load_dimensions()
    cases = load_cases(CASES_DIR, {name for name in dir(cls) if not name.startswith("_")})
    state = burndown.current_state()
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    sg = cls(creds.site, script_name=creds.script_name, api_key=creds.api_key)
    clients: dict[str, Any] = {"script": sg}
    if creds.login and creds.password:
        clients["user"] = cls(creds.site, login=creds.login, password=creds.password)
    try:
        creds = replace(creds, session_token=sg.get_session_token())
        clients["session"] = sg
    except Exception as exc:  # session cases are then blocked
        print(f"no session token: {type(exc).__name__}: {exc}", file=sys.stderr)
    schema = snapshot_schema(sg)
    editable = sorted(dt for dt, can_edit in schema["data_types"].items() if can_edit)
    fields = fixtures.ensure_fields(sg, editable)
    fx = fixtures.start_run(sg, run_id, fields, creds.login)
    secrets = {"login": creds.login, "password": creds.password}
    ca_certs = str(Path(inspect.getfile(cls)).parent / "lib" / "certifi" / "cacert.pem")
    contexts = {
        side: {**fx.for_side(side), "secrets": secrets, "ca_certs": ca_certs}
        for side in fixtures.SIDES
    }
    created: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    workdir = Path(tempfile.mkdtemp(prefix="fpt-parity-"))
    try:
        run_cli = subprocess_cli(creds, workdir)
        for case in cases:
            record = run_case(
                case,
                clients=clients,
                contexts=contexts,
                run_cli=run_cli,
                schema_fields=schema["fields"],
                dimensions=dimensions,
                cls=cls,
                created=created,
            )
            records.append(record)
            print(f"{record['status']:9} {record['id']}", flush=True)
    finally:
        retire_failures = fixtures.finish_run(sg, fx, created)
        shutil.rmtree(workdir, ignore_errors=True)
    results = {
        "run_id": run_id,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": state,
        "schema": schema,
        "fixtures": {
            "fields": fields.fields,
            "fields_created": fields.created,
            "fields_refused": fields.refused,
            "writes_refused": fx.write_refused,
            "retire_failures": retire_failures,
        },
        "cases": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(results, indent=2, sort_keys=True)
    (RESULTS_DIR / f"{run_id}.json").write_text(text, encoding="utf-8")
    (RESULTS_DIR / "latest.json").write_text(text, encoding="utf-8")
    totals: dict[str, int] = {}
    for record in records:
        totals[record["status"]] = totals.get(record["status"], 0) + 1
    print(f"\n{len(records)} cases: {json.dumps(totals)}. Retire failures: {len(retire_failures)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
