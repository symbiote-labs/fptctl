"""Print the public API of the installed shotgun_api3 as JSON.

It uses the parity inventory's rule for what counts: every public callable on Shotgun, and the
constructor. It imports nothing from fptctl, so it can run in a throw-away environment that holds
only one library version:

    uv run --no-project --with shotgun-api3==3.10.5 python scripts/api_signatures.py
"""

from __future__ import annotations

import inspect
import json
from typing import Any


def signatures() -> dict[str, Any]:
    import shotgun_api3

    def describe(signature: inspect.Signature) -> dict[str, Any]:
        parameters = [p for p in signature.parameters.values() if p.name != "self"]
        return {
            "signature": str(signature.replace(parameters=parameters)),
            "params": [p.name for p in parameters],
        }

    methods = {
        name: describe(inspect.signature(member))
        for name, member in inspect.getmembers(shotgun_api3.Shotgun, callable)
        if not name.startswith("_")
    }
    return {
        "version": shotgun_api3.__version__,
        "constructor": describe(inspect.signature(shotgun_api3.Shotgun)),
        "methods": methods,
    }


if __name__ == "__main__":
    print(json.dumps(signatures(), indent=2, sort_keys=True))
