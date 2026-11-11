"""Error types, exit codes, and structured error output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import IntEnum
from typing import Any, TextIO


class ExitCode(IntEnum):
    OK = 0
    UNEXPECTED = 1
    USAGE = 2
    AUTH = 3
    NOT_FOUND = 4
    API_FAULT = 5
    NETWORK = 6


class FptError(Exception):
    """Base class for every error fptctl reports to the user."""

    exit_code: ExitCode = ExitCode.UNEXPECTED
    error_type: str = "unexpected"

    def __init__(self, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})


class UsageError(FptError):
    exit_code = ExitCode.USAGE
    error_type = "usage"


class AuthError(FptError):
    exit_code = ExitCode.AUTH
    error_type = "auth"


class NotFoundError(FptError):
    exit_code = ExitCode.NOT_FOUND
    error_type = "not_found"


class ApiFaultError(FptError):
    exit_code = ExitCode.API_FAULT
    error_type = "api_fault"


class NetworkError(FptError):
    exit_code = ExitCode.NETWORK
    error_type = "network"


def error_payload(err: FptError) -> dict[str, Any]:
    return {"error": {"type": err.error_type, "message": err.message, "details": err.details}}


def emit_error(err: FptError, stream: TextIO, *, is_tty: bool) -> None:
    if is_tty:
        stream.write(f"error: {err.message}\n")
    else:
        stream.write(json.dumps(error_payload(err), default=str) + "\n")
