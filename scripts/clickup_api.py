"""Shared ClickUp REST v2 helpers — token loading and JSON requests.

Standard library only (this machine has no `requests`), and the project itself is
stdlib-first, so keep it that way.

Token: read from the repo-root `.env` FIRST, then fall back to the environment.
That order is deliberate — the CLICKUP_API_TOKEN environment variable on this
machine holds a rotated token that returns HTTP 401, while `.env` holds the
working one. Preferring the environment would fail in a way that looks like a
ClickUp outage rather than a stale credential.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.clickup.com/api/v2"


class ClickUpError(RuntimeError):
    """An API call failed. The message carries the status and response body."""


def force_utf8_stdout():
    """ClickUp task and list names contain characters cp1252 cannot encode.

    Without this, printing a task list dies mid-output on Windows with a
    UnicodeEncodeError that looks like a script bug rather than a console codec.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def find_repo_root(start=None):
    """Walk up from `start` looking for the directory that holds `.git`."""
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def _read_env_file(path, key):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=\s*(.*)$", re.M)
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip().split(" #")[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def load_token(explicit=None):
    """Return the ClickUp personal token, or raise with a fixable message."""
    if explicit:
        return explicit.strip()

    for path in token_locations():
        token = _read_env_file(path, "CLICKUP_API_TOKEN")
        if token:
            return token

    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    if token:
        return token

    looked = "\n  ".join(str(p) for p in token_locations())
    raise ClickUpError(
        "No CLICKUP_API_TOKEN found. Looked in:\n  " + looked +
        "\nand in the environment.\nRun token_setup.py --status for a diagnosis, or "
        "token_setup.py --save --target <repo-env|claude-env|user> to store one."
    )


def token_locations():
    """Every file `load_token` reads, in priority order.

    The repo `.env` wins over the environment on purpose: the CLICKUP_API_TOKEN
    environment variable on this machine holds a rotated token that 401s, and
    preferring it makes a stale credential look like a ClickUp outage.

    The user-level file comes last but matters most on a shared repository — it
    keeps a personal token out of the working tree entirely.
    """
    root = find_repo_root(Path(__file__).parent)
    return [
        root / ".env",
        root / ".claude" / ".env",
        Path.cwd() / ".env",
        Path.home() / ".claude" / "clickup.env",
    ]


def mask(token):
    """`pk_113550513_ABC...XYZ` -> `pk_…XYZ4`. Never print a token unmasked."""
    if not token:
        return "(none)"
    tail = token[-4:] if len(token) >= 4 else "?"
    return f"{token[:3]}…{tail} ({len(token)} chars)"


def request(method, path, token, payload=None, query=None, timeout=60):
    """Call the ClickUp REST v2 API and return the decoded JSON body."""
    url = API + path
    if query:
        url += "?" + urllib.parse.urlencode(query)

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    # ClickUp personal tokens go in Authorization *without* a Bearer prefix.
    req.add_header("Authorization", token)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        hint = ""
        if exc.code == 401:
            hint = ("\nHint: 401 usually means the token is stale. The working token "
                    "lives in the repo-root .env, not in the environment.")
        raise ClickUpError(f"{method} {path} -> HTTP {exc.code}: {detail}{hint}") from None
    except urllib.error.URLError as exc:
        raise ClickUpError(f"{method} {path} -> network error: {exc.reason}") from None

    return json.loads(body) if body.strip() else {}
