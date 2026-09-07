"""Diagnose and store the ClickUp API token the push scripts need.

    python token_setup.py --status
    python token_setup.py --save --target repo-env|claude-env|user

`--status` says whether a token is present and whether it actually works, without
ever printing it. That distinction matters: a token can be found and still be
dead, and "found" alone has misled this project before — the CLICKUP_API_TOKEN
environment variable holds a rotated token that returns 401 while the repo `.env`
holds the working one.

`--save` reads the token from the CLICKUP_TOKEN_INPUT environment variable rather
than a command-line argument, writes it to the chosen file, and verifies it
against the API. It refuses to write anywhere git would track, because a token
committed to a shared repository is a token that must be rotated.

A token is a credential. This script never prints one, and never writes one to a
file that is not git-ignored.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from clickup_api import (ClickUpError, find_repo_root, force_utf8_stdout, mask,
                         request, token_locations, _read_env_file)

TARGETS = {
    "repo-env": ("the repo-root .env, alongside the app config",
                 lambda root: root / ".env"),
    "claude-env": ("a .claude/.env, keeping ClickUp separate from the app config",
                   lambda root: root / ".claude" / ".env"),
    "user": ("your home directory, outside the repository entirely",
             lambda root: Path.home() / ".claude" / "clickup.env"),
}


def is_git_ignored(path):
    """True when git would ignore this path. None when it is outside any repo."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=str(path.parent if path.parent.exists() else Path.cwd()),
            capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None  # 128 = not a git repository


def verify(token):
    """Return (ok, description). Calls GET /user, the cheapest authenticated read."""
    try:
        me = request("GET", "/user", token, timeout=30).get("user", {})
    except ClickUpError as exc:
        return False, str(exc).split("\n")[0]
    who = me.get("username") or me.get("email") or "unknown user"
    return True, f"{who} (ClickUp id {me.get('id')})"


def status():
    print("Searching every location the push scripts read, in priority order:\n")
    found_any = False
    for path in token_locations():
        token = _read_env_file(path, "CLICKUP_API_TOKEN")
        if token:
            found_any = True
            ok, detail = verify(token)
            mark = "WORKS" if ok else "DEAD "
            print(f"  [{mark}] {path}")
            print(f"           {mask(token)} -> {detail}")
        else:
            why = "no CLICKUP_API_TOKEN line" if path.exists() else "file does not exist"
            print(f"  [  -  ] {path}   ({why})")

    env_token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    if env_token:
        found_any = True
        ok, detail = verify(env_token)
        print(f"  [{'WORKS' if ok else 'DEAD '}] $CLICKUP_API_TOKEN (environment)")
        print(f"           {mask(env_token)} -> {detail}")
    else:
        print("  [  -  ] $CLICKUP_API_TOKEN (environment)   (not set)")

    print()
    if not found_any:
        print("No token anywhere. Store one with:")
        print("  CLICKUP_TOKEN_INPUT=pk_... python token_setup.py --save --target user")
        return 1

    try:
        effective = __import__("clickup_api").load_token()
    except ClickUpError:
        return 1
    ok, detail = verify(effective)
    print(f"Effective token (the one the push will use): {mask(effective)}")
    print(f"  -> {'valid, authenticates as ' + detail if ok else 'REJECTED: ' + detail}")
    if not ok:
        print("\nA dead token earlier in the list shadows a working one later in it. "
              "Remove the dead line, or re-save over it with --save.")
    return 0 if ok else 1


def save(target):
    label, resolve = TARGETS[target]
    token = os.environ.get("CLICKUP_TOKEN_INPUT", "").strip()
    if not token:
        print("ERROR: pass the token via the CLICKUP_TOKEN_INPUT environment variable, "
              "not as an argument:\n"
              "  CLICKUP_TOKEN_INPUT=pk_... python token_setup.py --save --target "
              + target, file=sys.stderr)
        return 1

    if not token.startswith("pk_"):
        print(f"WARN: a ClickUp personal token normally starts with 'pk_'; this one does "
              f"not ({mask(token)}). Continuing, but check you pasted the right value.")

    path = resolve(find_repo_root(Path(__file__).parent))

    ignored = is_git_ignored(path)
    if ignored is False:
        print(f"ERROR: refusing to write a token to {path}\n"
              "git does NOT ignore that path, so the token would be committed and would "
              "then have to be rotated. Add it to .gitignore first, or use "
              "--target user to store it outside the repository.", file=sys.stderr)
        return 1

    ok, detail = verify(token)
    if not ok:
        print(f"ERROR: refusing to save a token ClickUp rejects.\n  {detail}\n"
              "Check you copied the whole value from ClickUp -> Settings -> Apps.",
              file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"CLICKUP_API_TOKEN={token}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        replaced = False
        for i, existing in enumerate(lines):
            if existing.strip().startswith("CLICKUP_API_TOKEN="):
                lines[i], replaced = line, True
                break
        if not replaced:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append("# ClickUp personal token, used by the write-ticket skill")
            lines.append(line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        action = "updated in" if replaced else "appended to"
    else:
        path.write_text("# ClickUp personal token, used by the write-ticket skill\n"
                        + line + "\n", encoding="utf-8")
        action = "created"

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    print(f"Token {action} {path}")
    print(f"  {mask(token)} -> authenticates as {detail}")
    print(f"  location: {label}")
    print(f"  git-ignored: {'yes' if ignored else 'outside any repository'}")

    shadowing = [p for p in token_locations()
                 if p != path and _read_env_file(p, "CLICKUP_API_TOKEN")]
    earlier = [p for p in shadowing if token_locations().index(p) < token_locations().index(path)]
    if earlier:
        print("\nNOTE: these are read BEFORE the file just written, so one of them still "
              "wins:\n  " + "\n  ".join(str(p) for p in earlier) +
              "\nRun --status to see which token is actually effective.")
    return 0


def main():
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true",
                        help="report where a token is found and whether it works")
    parser.add_argument("--save", action="store_true",
                        help="store the token from $CLICKUP_TOKEN_INPUT")
    parser.add_argument("--target", choices=sorted(TARGETS),
                        help="where to store it (required with --save)")
    args = parser.parse_args()

    if args.save:
        if not args.target:
            print("ERROR: --save needs --target. Options:", file=sys.stderr)
            for name, (label, _) in sorted(TARGETS.items()):
                print(f"  {name:<12} {label}", file=sys.stderr)
            return 1
        return save(args.target)
    return status()


if __name__ == "__main__":
    sys.exit(main())
