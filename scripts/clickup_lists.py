"""Show the real ClickUp destinations a ticket can be pushed to.

Two modes:

  python clickup_lists.py                 walk the workspace and print every list
  python clickup_lists.py --inspect <id>  show one list's statuses + custom fields

The walk exists because sprint lists are created and closed constantly — a
hardcoded "Sprint 5" id is wrong the week Sprint 6 opens, and pushing a ticket
into last sprint's list is close to invisible until someone goes looking for it.

--inspect matters because status sets differ per list: the backlog lists start at
`draft`, the sprint lists start at `to do`. Sending the wrong one makes the create
call fail, so read the real statuses before building the push command.
"""

import argparse
import json
import sys

from clickup_api import ClickUpError, force_utf8_stdout, load_token, request


def walk(token, space_filter=None, include_archived=False):
    """Return [{team, space, folder, name, id}] for every list in the workspace."""
    archived = "true" if include_archived else "false"
    rows = []

    teams = request("GET", "/team", token).get("teams", [])
    for team in teams:
        spaces = request("GET", f"/team/{team['id']}/space", token,
                         query={"archived": archived}).get("spaces", [])
        for space in spaces:
            if space_filter and space_filter.lower() not in space["name"].lower():
                continue

            folders = request("GET", f"/space/{space['id']}/folder", token,
                              query={"archived": archived}).get("folders", [])
            for folder in folders:
                for lst in folder.get("lists", []):
                    rows.append({
                        "team": team["name"], "space": space["name"],
                        "folder": folder["name"], "name": lst["name"], "id": lst["id"],
                        "task_count": lst.get("task_count"),
                    })

            loose = request("GET", f"/space/{space['id']}/list", token,
                            query={"archived": archived}).get("lists", [])
            for lst in loose:
                rows.append({
                    "team": team["name"], "space": space["name"],
                    "folder": None, "name": lst["name"], "id": lst["id"],
                    "task_count": lst.get("task_count"),
                })
    return rows


def print_table(rows):
    if not rows:
        print("No lists found. Check the token's workspace access.")
        return
    width = max(len(r["id"]) for r in rows)
    print(f"{'LIST_ID'.ljust(width)}  DESTINATION")
    print(f"{'-' * width}  {'-' * 60}")
    for row in rows:
        path = " / ".join(p for p in (row["space"], row["folder"], row["name"]) if p)
        count = f"  ({row['task_count']} tasks)" if row["task_count"] is not None else ""
        print(f"{row['id'].ljust(width)}  {path}{count}")


def inspect(token, list_id):
    lst = request("GET", f"/list/{list_id}", token)
    print(f"List: {lst.get('name')}   (id {lst.get('id')})")
    folder = (lst.get("folder") or {}).get("name")
    space = (lst.get("space") or {}).get("name")
    print(f"Path: {' / '.join(p for p in (space, folder) if p and p != 'hidden')}")

    statuses = [s["status"] for s in lst.get("statuses", [])]
    print("\nStatuses (use one of these exactly, --status):")
    for status in statuses:
        print(f"  - {status}")
    if statuses:
        print(f"\nDefault for a new ticket on this list: {statuses[0]!r}")

    fields = request("GET", f"/list/{list_id}/field", token).get("fields", [])
    print(f"\nCustom fields ({len(fields)}):")
    if not fields:
        print("  (none — hours go into the native time_estimate instead)")
    for field in fields:
        line = f"  - {field['name']}  [{field['type']}]"
        options = (field.get("type_config") or {}).get("options") or []
        if options:
            names = ", ".join(o.get("name") or o.get("label", "?") for o in options)
            line += f"  options: {names}"
        print(line)


def main():
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inspect", metavar="LIST_ID",
                        help="show statuses and custom fields for one list")
    parser.add_argument("--space", help="only walk spaces whose name contains this")
    parser.add_argument("--archived", action="store_true", help="include archived spaces/lists")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--token", help="override the token (normally read from .env)")
    args = parser.parse_args()

    try:
        token = load_token(args.token)
        if args.inspect:
            inspect(token, args.inspect)
            return 0
        rows = walk(token, args.space, args.archived)
        if args.as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            print_table(rows)
        return 0
    except ClickUpError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
