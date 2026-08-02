"""Small TLS-aware status probe for the public runtime supervisor.

Windows PowerShell's Invoke-WebRequest can reject a healthy Cloudflare quick
tunnel during TLS negotiation on some hosts.  This helper uses the Python
runtime that launches the API, requires normal certificate validation, and
returns success only for a JSON status response with HTTP 200.
"""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main() -> int:
    arguments = sys.argv[1:]
    emit_json = arguments[:1] == ["--json"]
    if emit_json:
        arguments = arguments[1:]
    if len(arguments) != 1:
        return 2
    try:
        with urlopen(arguments[0], timeout=12) as response:  # nosec B310 - URL is supplied by the local supervisor
            if response.status != 200:
                return 1
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") != "ok":
                return 1
            if emit_json:
                print(json.dumps(payload, separators=(",", ":")))
            return 0
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
