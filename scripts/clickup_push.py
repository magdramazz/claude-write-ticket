"""Push a backlog ticket markdown file to ClickUp as a task.

    python clickup_push.py --file <absolute path to _specs/<slug>.md> --list <list_id> [opts]

Runs from any working directory. Pass --file as an absolute path: it is resolved against the
current directory, not against this script.

What goes where, and why:

  Task name          <- the metadata table's **Title** row (fallback: the H1)
  Description        <- the body from `## User Story` up to the Ticket Quality
                        Checklist. The metadata table is deliberately NOT sent:
                        every row of it is already a real ClickUp field, and a
                        second copy inside the description silently drifts out of
                        sync with the field it duplicates.
  Status             <- --status, else the metadata Status mapped onto the list's
                        real status set (backlog lists start at `draft`, sprint
                        lists at `to do`)
  time_estimate      <- the metadata **Time Estimate (h)** row, in milliseconds
  Checklist          <- the Ticket Quality Checklist items, as a real ClickUp
                        checklist (only with --checklist)
  Implementation notes are never sent - they are notes to the implementer that
                        live with the local file.

Custom fields are set one call at a time AFTER the task exists, so a rejected
field value costs you that field, not the whole ticket.
"""

import argparse
import re
import sys
from pathlib import Path

from clickup_api import ClickUpError, force_utf8_stdout, load_token, request

BODY_START = re.compile(r"^#{1,3}\s+User Story\s*$", re.I)
CHECKLIST_HEAD = re.compile(r"^#{1,3}\s+Ticket Quality Checklist\s*$", re.I)
NOTES_HEAD = re.compile(r"^#{1,3}\s+Implementation notes", re.I)
META_ROW = re.compile(r"^\|\s*\*\*(?P<key>[^*|]+)\*\*\s*\|\s*(?P<val>.*?)\s*\|\s*$")
CHECK_ITEM = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")
WARN_SIGN = "⚠"

# The standard's status names do not exist on every list. Map them onto whatever
# the target list actually offers, so a ticket written as `Backlog` still lands.
STATUS_SYNONYMS = {
    "backlog": ["draft", "to do", "todo", "open"],
    "planned": ["ready for sprint", "to do", "todo", "draft"],
    "todo": ["to do", "todo", "draft", "open"],
    "to do": ["to do", "todo", "draft", "open"],
    "in progress": ["in progress"],
}


def parse_ticket(text):
    """Pull the pushable parts out of a ticket markdown file."""
    lines = text.splitlines()

    meta = {}
    for line in lines:
        match = META_ROW.match(line)
        if match:
            meta.setdefault(match.group("key").strip(), match.group("val").strip())

    start = next((i for i, l in enumerate(lines) if BODY_START.match(l)), None)
    if start is None:
        raise ValueError(
            "No `## User Story` heading found. The push starts there by design - "
            "check the file follows the Backlog Ticket Standard."
        )

    stop = next((i for i, l in enumerate(lines[start:], start)
                 if CHECKLIST_HEAD.match(l) or NOTES_HEAD.match(l)), len(lines))
    body = "\n".join(lines[start:stop]).rstrip()
    body = re.sub(r"\n+-{3,}\s*$", "", body).rstrip()

    checklist = []
    head = next((i for i, l in enumerate(lines) if CHECKLIST_HEAD.match(l)), None)
    if head is not None:
        for line in lines[head + 1:]:
            if NOTES_HEAD.match(line) or re.match(r"^#{1,3}\s+\S", line):
                break
            item = CHECK_ITEM.match(line)
            if item:
                checklist.append({
                    "name": item.group("text"),
                    "resolved": item.group("mark").lower() == "x",
                })

    title = meta.get("Title") or next(
        (l[2:].strip() for l in lines if l.startswith("# ")), None)
    if not title:
        raise ValueError("No Title in the metadata table and no H1 heading to fall back on.")

    return {
        "title": re.split(WARN_SIGN, title)[0].strip(),
        "meta": meta,
        "body": body,
        "checklist": checklist,
    }


def hours_from(value):
    """`6 (estimate - four endpoints)` -> 6.0. Returns None when there is no number."""
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group()) if match else None


def resolve_status(wanted, available):
    """Pick a status that exists on the target list, or explain why none fits."""
    lowered = {s.lower(): s for s in available}
    if wanted:
        key = re.split(WARN_SIGN, wanted)[0].strip().lower()
        if key in lowered:
            return lowered[key], "matched the ticket's Status %r" % wanted
        for candidate in STATUS_SYNONYMS.get(key, []):
            if candidate in lowered:
                return lowered[candidate], "mapped %r -> %r" % (wanted, lowered[candidate])
    if not available:
        return None, "the list reported no statuses"
    return available[0], "no match for %r; fell back to the list's first status" % wanted


def coerce_field_value(field, raw):
    """Turn a human-typed value into the shape ClickUp wants for this field type."""
    kind = field.get("type")
    options = (field.get("type_config") or {}).get("options") or []

    if kind == "number":
        return float(raw) if "." in str(raw) else int(raw)
    if kind == "checkbox":
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if kind in ("drop_down", "labels"):
        for option in options:
            name = option.get("name") or option.get("label") or ""
            if name.strip().lower() == str(raw).strip().lower():
                return [option["id"]] if kind == "labels" else option["id"]
        names = ", ".join(o.get("name") or o.get("label", "?") for o in options)
        raise ValueError("%r is not an option of %r. Options: %s"
                         % (raw, field["name"], names))
    if kind == "users":
        return {"add": [int(part) for part in re.split(r"[,\s]+", str(raw)) if part]}
    return str(raw)


def plan_custom_fields(fields, requested, hours, assignee_ids):
    """Return ([{field, value, why}], [warnings]) - explicit asks plus safe auto-maps."""
    by_name = {f["name"].strip().lower(): f for f in fields}
    planned, warnings, claimed = [], [], set()

    for item in requested:
        if "=" not in item:
            warnings.append("--custom-field %r is not in Name=Value form; skipped" % item)
            continue
        name, raw = item.split("=", 1)
        field = by_name.get(name.strip().lower())
        if not field:
            warnings.append("the list has no custom field named %r; skipped" % name.strip())
            continue
        try:
            planned.append({"field": field, "value": coerce_field_value(field, raw.strip()),
                            "why": "you asked for it"})
            claimed.add(field["id"])
        except ValueError as exc:
            warnings.append("%s; skipped" % exc)

    # Two auto-maps worth doing because these lists carry a custom field that
    # shadows a native one, and a ticket that fills only the native half reads as
    # unestimated / unassigned in the board views the team actually uses.
    for field in fields:
        if field["id"] in claimed:
            continue
        name = field["name"].strip().lower()
        if hours is not None and field.get("type") == "number" and name.startswith("time estimate"):
            planned.append({"field": field, "value": hours,
                            "why": "auto: mirrors the native time estimate"})
        elif assignee_ids and field.get("type") == "users" and "assignee" in name:
            planned.append({"field": field, "value": {"add": list(assignee_ids)},
                            "why": "auto: mirrors the native assignee"})
    return planned, warnings


def resolve_assignees(values, token):
    """Turn --assignee values into ClickUp user ids, resolving 'me' via the token.

    'me' exists because this skill is shared across the team. A hardcoded id in the
    documented defaults would quietly assign every teammate's tickets to whoever
    wrote those defaults, and nobody would notice until the board looked wrong.
    """
    resolved = []
    for value in values:
        text = str(value).strip()
        if text.lower() == "me":
            me = request("GET", "/user", token).get("user", {})
            if not me.get("id"):
                raise ValueError("could not resolve 'me' — GET /user returned no id")
            resolved.append(int(me["id"]))
        else:
            try:
                resolved.append(int(text))
            except ValueError:
                raise ValueError("--assignee takes a numeric ClickUp user id or 'me', "
                                 "got %r" % text) from None
    return resolved


def update_md_id(path, task_id, url):
    """Fill the standard's `ID` row with the real task id, so the file points at ClickUp."""
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"(^\|\s*\*\*ID\*\*\s*\|\s*).*?(\s*\|\s*$)",
        lambda m: "%s[%s](%s)%s" % (m.group(1), task_id, url, m.group(2)),
        text, count=1, flags=re.M)
    if count:
        path.write_text(new_text, encoding="utf-8")
    return bool(count)


def main():
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, help="path to the ticket .md")
    parser.add_argument("--list", required=True, dest="list_id", help="target ClickUp list id")
    parser.add_argument("--status", help="exact status name (default: mapped from the ticket)")
    parser.add_argument("--assignee", action="append", default=[], metavar="ID|me",
                        help="ClickUp user id, or 'me' for whoever the token belongs to; "
                             "repeatable. Prefer 'me' — a hardcoded id assigns every "
                             "teammate's tickets to one person")
    parser.add_argument("--tag", action="append", default=[], help="tag name; repeatable")
    parser.add_argument("--time-estimate", type=float, dest="hours",
                        help="hours (default: the ticket's Time Estimate row)")
    parser.add_argument("--custom-field", action="append", default=[], metavar="NAME=VALUE",
                        help="set a list custom field; repeatable")
    parser.add_argument("--checklist", action="store_true",
                        help="also create the Ticket Quality Checklist (~1 call per item)")
    parser.add_argument("--no-update-md", action="store_true",
                        help="do not write the new task id back into the .md")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve and print everything, create nothing")
    parser.add_argument("--token", help="override the token (normally read from .env)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print("ERROR: no such file: %s" % path, file=sys.stderr)
        return 1

    try:
        ticket = parse_ticket(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    try:
        token = load_token(args.token)
        assignees = resolve_assignees(args.assignee, token)
        target = request("GET", "/list/%s" % args.list_id, token)
        fields = request("GET", "/list/%s/field" % args.list_id, token).get("fields", [])
    except (ClickUpError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    args.assignee = assignees

    statuses = [s["status"] for s in target.get("statuses", [])]
    if args.status and args.status.lower() not in [s.lower() for s in statuses]:
        print("ERROR: %r is not a status on this list. Valid: %s" % (args.status, statuses),
              file=sys.stderr)
        return 1
    status, status_why = resolve_status(args.status or ticket["meta"].get("Status"), statuses)

    hours = args.hours if args.hours is not None else hours_from(
        ticket["meta"].get("Time Estimate (h)") or ticket["meta"].get("Time Estimate"))
    planned, warnings = plan_custom_fields(fields, args.custom_field, hours, args.assignee)

    payload = {"name": ticket["title"], "markdown_description": ticket["body"]}
    if status:
        payload["status"] = status
    if args.assignee:
        payload["assignees"] = args.assignee
    if args.tag:
        payload["tags"] = args.tag
    if hours is not None:
        payload["time_estimate"] = int(hours * 3600 * 1000)

    print("Ticket : %s" % ticket["title"])
    print("Target : %s  (list %s)" % (target.get("name"), args.list_id))
    print("Status : %r  - %s" % (status, status_why))
    print("Hours  : %s   Assignees: %s   Tags: %s"
          % (hours, args.assignee or "-", args.tag or "-"))
    print("Body   : %d chars, starts at '## User Story'" % len(ticket["body"]))
    print("Checklist items parsed: %d  (will %s them)"
          % (len(ticket["checklist"]), "create" if args.checklist else "NOT create"))
    for item in planned:
        print("Field  : %s = %s  (%s)" % (item["field"]["name"], item["value"], item["why"]))
    for warning in warnings:
        print("WARN   : %s" % warning)

    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    try:
        task = request("POST", "/list/%s/task" % args.list_id, token, payload=payload)
    except ClickUpError as exc:
        print("ERROR: creating the task failed: %s" % exc, file=sys.stderr)
        return 1

    task_id, url = task["id"], task.get("url", "")
    print("\nCreated %s  %s" % (task_id, url))

    for item in planned:
        try:
            request("POST", "/task/%s/field/%s" % (task_id, item["field"]["id"]), token,
                    payload={"value": item["value"]})
            print("  set custom field %r" % item["field"]["name"])
        except ClickUpError as exc:
            print("  WARN: custom field %r not set: %s" % (item["field"]["name"], exc))

    if args.checklist and ticket["checklist"]:
        try:
            checklist = request("POST", "/task/%s/checklist" % task_id, token,
                                payload={"name": "Ticket Quality Checklist"})
            checklist_id = checklist["checklist"]["id"]
            for entry in ticket["checklist"]:
                request("POST", "/checklist/%s/checklist_item" % checklist_id, token,
                        payload={"name": entry["name"], "resolved": entry["resolved"]})
            print("  added checklist with %d items" % len(ticket["checklist"]))
        except ClickUpError as exc:
            print("  WARN: checklist not fully created: %s" % exc)

    if not args.no_update_md:
        if update_md_id(path, task_id, url):
            print("  wrote the task id back into %s" % path)

    print("\nDone: %s" % url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
