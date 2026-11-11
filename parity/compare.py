"""Parity comparison. Implements the wire format again, independently of fpt (spec, "Wire format").

Changing this file needs the owner's approval once it is in use
(spec, "Rules for the executing agent").
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Changing this set needs the owner's approval (spec, "Masks").
MASK_ALLOWLIST: frozenset[str] = frozenset({"id", "created_at", "updated_at"})

MODES = ("identical", "mirrored", "bytes", "error")
PASS, FAILING, UNSTABLE, BLOCKED = "pass", "failing", "unstable", "blocked"

_EXIT_BY_CLASS_NAME: dict[str, int] = {
    **dict.fromkeys(
        (
            "AuthenticationFault",
            "MissingTwoFactorAuthenticationFault",
            "UserCredentialsNotAllowedForSSOAuthenticationFault",
            "UserCredentialsNotAllowedForOxygenAuthenticationFault",
        ),
        3,
    ),
    **dict.fromkeys(
        ("Fault", "ShotgunError", "ShotgunFileDownloadError", "ShotgunThumbnailNotReady"), 5
    ),
    **dict.fromkeys(
        (
            "ProtocolError",
            "HttpLib2Error",
            "ConnectionError",
            "TimeoutError",
            "gaierror",
            "herror",
            "SSLError",
        ),
        6,
    ),
    **dict.fromkeys(("ValueError", "TypeError"), 2),
}


@dataclass(frozen=True)
class DirectError:
    classes: tuple[str, ...]  # class names from the MRO, nearest first
    message: str


@dataclass(frozen=True)
class Observation:
    """Everything the runner saw for one case. Values are wire format unless noted."""

    mode: str
    method: str
    expected_args: Mapping[str, Any]
    trace: Sequence[Mapping[str, Any]]
    exit_code: int
    stdout: bytes
    stderr: str
    masks: frozenset[str] = frozenset()
    direct: Any = None  # bytes in "bytes" mode
    direct_again: Any = None
    direct_readback: Any = None
    cli_readback: Any = None
    direct_error: DirectError | None = None
    result_type: str | None = None  # mirrored only: an int result is an id of this entity type


@dataclass(frozen=True)
class Outcome:
    status: str
    problems: tuple[str, ...] = field(default=())


def wire(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return list(map(wire, value))
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("non-string key")
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, dt.datetime):
        if value.utcoffset() is None:
            return value.replace(microsecond=0).isoformat()
        utc = value.astimezone(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
        return utc.isoformat() + "Z"
    if isinstance(value, dt.date):
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    raise TypeError(f"no wire form for {type(value).__name__}")


def check_masks(masks: Iterable[str]) -> frozenset[str]:
    requested = frozenset(masks)
    rejected = sorted(requested - MASK_ALLOWLIST)
    if rejected:
        raise ValueError(f"masks not on the allowlist: {', '.join(rejected)}")
    return requested


def apply_masks(value: Any, masks: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {k: apply_masks(v, masks) for k, v in value.items() if k not in masks}
    if isinstance(value, list):
        return [apply_masks(item, masks) for item in value]
    return value


def as_entity(value: Any, result_type: str | None) -> Any:
    """A bare int result is an entity id: compare it as a link, so the `id` mask applies."""
    if result_type is None or isinstance(value, bool) or not isinstance(value, int):
        return value
    return {"type": result_type, "id": value}


def diff(direct: Any, cli: Any, path: str = "$") -> list[str]:
    if isinstance(direct, dict) and isinstance(cli, dict):
        problems: list[str] = []
        for key in sorted(set(direct) | set(cli)):
            where = f"{path}.{key}"
            if key not in cli:
                problems.append(f"{where}: missing from CLI output")
            elif key not in direct:
                problems.append(f"{where}: only in CLI output")
            else:
                problems.extend(diff(direct[key], cli[key], where))
        return problems
    if isinstance(direct, list) and isinstance(cli, list):
        if len(direct) != len(cli):
            return [f"{path}: direct has {len(direct)} items, CLI has {len(cli)}"]
        return [
            p
            for i, (d, c) in enumerate(zip(direct, cli, strict=True))
            for p in diff(d, c, f"{path}[{i}]")
        ]
    if isinstance(direct, bool) != isinstance(cli, bool) or direct != cli:
        return [f"{path}: direct {json.dumps(direct)}, CLI {json.dumps(cli)}"]
    return []


def expected_exit_code(mro: Sequence[str]) -> int:
    for name in mro:
        if name in _EXIT_BY_CLASS_NAME:
            return _EXIT_BY_CLASS_NAME[name]
    return 1


def _request_problems(obs: Observation) -> list[str]:
    calls = [line for line in obs.trace if "call" in line]
    if len(calls) != 1:
        return [f"request: expected exactly one library call, the trace has {len(calls)}"]
    if calls[0]["call"] != obs.method:
        return [f"request: expected {obs.method}, the CLI called {calls[0]['call']}"]
    return [f"request {p}" for p in diff(dict(obs.expected_args), calls[0]["args"])]


def _success_problems(obs: Observation) -> list[str]:
    problems = []
    if obs.exit_code != 0:
        problems.append(f"exit code {obs.exit_code}, stderr: {obs.stderr.strip()}")
    elif obs.stderr:
        problems.append(f"stderr is not empty: {obs.stderr.strip()}")
    if obs.direct is None or obs.direct in ([], {}, b""):
        problems.append("the direct result is empty, which proves nothing")
    return problems


def _parse(stdout: bytes) -> tuple[Any, list[str]]:
    try:
        return json.loads(stdout), []
    except ValueError:
        return None, ["stdout is not JSON"]


def _judge_error(obs: Observation) -> Outcome:
    if obs.direct_error is None:
        return Outcome(FAILING, ("the direct call did not raise",))
    problems = _request_problems(obs)
    expected = expected_exit_code(obs.direct_error.classes)
    if obs.exit_code != expected:
        problems.append(f"exit code {obs.exit_code}, expected {expected}")
    if obs.stdout:
        problems.append("stdout is not empty")
    try:
        message = json.loads(obs.stderr)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return Outcome(FAILING, (*problems, "stderr is not one JSON error object"))
    wanted = obs.direct_error.message or obs.direct_error.classes[0]
    if message != wanted:
        problems.append(f"message {json.dumps(message)}, expected {json.dumps(wanted)}")
    return Outcome(FAILING if problems else PASS, tuple(problems))


def judge(obs: Observation) -> Outcome:
    if obs.mode not in MODES:
        raise ValueError(f"unknown mode {obs.mode!r}")
    masks = check_masks(obs.masks)
    if obs.mode == "error":
        return _judge_error(obs)
    if obs.direct_error is not None:
        return Outcome(
            BLOCKED,
            (f"direct call raised {obs.direct_error.classes[0]}: {obs.direct_error.message}",),
        )
    if obs.mode == "identical":
        unstable = diff(obs.direct, obs.direct_again)
        if unstable:
            return Outcome(UNSTABLE, tuple(unstable))
    problems = _request_problems(obs) + _success_problems(obs)
    if obs.mode == "bytes":
        direct_sha = hashlib.sha256(obs.direct or b"").hexdigest()
        cli_sha = hashlib.sha256(obs.stdout).hexdigest()
        if direct_sha != cli_sha:
            problems.append(f"sha256 direct {direct_sha}, CLI {cli_sha}")
    else:
        cli, parse_problems = _parse(obs.stdout)
        problems += parse_problems
        if not parse_problems:
            direct = as_entity(obs.direct, obs.result_type)
            cli = as_entity(cli, obs.result_type)
            problems += diff(apply_masks(direct, masks), apply_masks(cli, masks))
        if obs.mode == "mirrored":
            problems += [
                f"read-back {p}"
                for p in diff(
                    apply_masks(obs.direct_readback, masks), apply_masks(obs.cli_readback, masks)
                )
            ]
    return Outcome(FAILING if problems else PASS, tuple(problems))
