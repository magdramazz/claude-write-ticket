# Pushing a ticket to ClickUp

Read this at Phase 5, when a ticket file has been accepted and is going to ClickUp.

Three scripts live in `.claude/skills/write-ticket/scripts/` and share `clickup_api.py`:
`token_setup.py` (check/store the token), `clickup_lists.py` (find the destination) and
`clickup_push.py` (create the task). They are standard-library only — no `pip install`.

They run from any working directory — Python always puts a script's own directory on the
import path, so `clickup_api` resolves either way. What does *not* follow you around is
`--file`: it is resolved against the current directory, so pass it as an absolute path and
the question disappears.

```bash
# from the repo root
python .claude/skills/write-ticket/scripts/clickup_lists.py --space <SpaceName>

# or from the scripts directory
cd .claude/skills/write-ticket/scripts && python clickup_lists.py --space <SpaceName>
```

## The token

Start every push with:

```bash
python token_setup.py --status
```

It prints each location, whether a token is there, and whether that token actually
authenticates — masked, never in full. Use it before anything else: "found" and "works" are
different answers, and this project has already been bitten by the gap between them.

`clickup_api.load_token()` reads `CLICKUP_API_TOKEN` in this order:

1. repo-root `.env`
2. `.claude/.env`
3. `./.env` (whatever directory you ran from)
4. `~/.claude/clickup.env`
5. the `CLICKUP_API_TOKEN` environment variable

Files beat the environment on purpose: the environment variable on this machine holds a
rotated token that returns HTTP 401 while the repo `.env` holds the working one, and
preferring the environment turns a stale credential into what looks like a ClickUp outage.
The flip side is that a **dead token early in the list shadows a working one later** —
`--status` is what makes that visible.

### Storing a token

```bash
CLICKUP_TOKEN_INPUT=pk_... python token_setup.py --save --target user
```

`--target` is `user` (`~/.claude/clickup.env`, outside the repo — best for a personal token
in a shared repository), `repo-env` (repo-root `.env`), or `claude-env` (`.claude/.env`).

The token comes from `CLICKUP_TOKEN_INPUT` rather than a command-line argument, and before
writing anything the script verifies it against `GET /user` and runs `git check-ignore` on
the destination — it refuses to write a credential anywhere git would track it. It replaces
an existing `CLICKUP_API_TOKEN=` line rather than appending a duplicate, and warns when a
higher-priority file will still shadow what it just wrote.

Do not `grep` a token out of `.env` yourself — the permission classifier blocks reading
credentials that way, and the scripts already handle it. ClickUp personal tokens go in the
`Authorization` header with **no** `Bearer` prefix.

## Step 1 — find the destination

```bash
python clickup_lists.py                      # every list in the workspace
python clickup_lists.py --space <SpaceName>  # just one project's spaces
python clickup_lists.py --json               # machine-readable
```

Output is `LIST_ID  Space / Folder / List (n tasks)`. The task counts are a useful sanity
check: the live sprint is the one with tasks in it.

The lists usually sit in folders — `Sprint List` (one list per sprint) and `Backlog`
(`Product Backlog List`, `Bugs`, `Fixes & Technical Debt`). Which one a ticket belongs in is
the user's call, but the working convention is: feature stories to Product Backlog List,
test-coverage and technical-debt work to Fixes & Technical Debt, and anything being worked on
this sprint straight into the current sprint list.

## Step 2 — inspect the list

```bash
python clickup_lists.py --inspect <list_id>
```

Prints the list's real statuses and custom fields. This matters because the two families of
list do not share a status set:

- Backlog lists: `draft → refining → ready for sprint → blocked → complete`
- Sprint lists: `to do → in progress → in review → ready for qa → qa testing → done →
  blocked → Closed`

Neither has a status called `Backlog`, which is what `ticket-format.md` puts in the metadata
table. The
push script maps it (`Backlog → draft` on a backlog list, `Backlog → to do` on a sprint
list) and prints the mapping it chose, so read that line rather than assuming.

Custom fields differ just as much. Sprint lists carry one (`Business Value`); the backlog
lists carry nine, including `Work Item Type`, `Story Points`, `Priority`, `Risk Level`,
`Time Estimate (h)` and a `users`-typed `Assignee` that is separate from the native one.

## Step 3 — dry run

```bash
python clickup_push.py \
  --file "/path/to/.claude/_specs/<slug>.md" \
  --list <list_id> \
  --assignee me \
  --custom-field "Work Item Type=Task" \
  --checklist \
  --dry-run
```

`--dry-run` makes two read-only calls and creates nothing. It prints the resolved title,
the status and *why* it chose it, the hours, the body size, how many checklist items it
parsed, and every custom field it will set. Read it before the real push — a wrong list id
is free to fix here and awkward to fix once the team can see the task.

Drop `--dry-run` to create the task.

## What the script maps

| Ticket file | ClickUp |
|---|---|
| `\| **Title** \|` row (fallback: the H1) | task name |
| `## User Story` → just before the Ticket Quality Checklist | `markdown_description` |
| `\| **Status** \|` row, mapped to the list's statuses | task status |
| `\| **Time Estimate (h)** \|` row | native `time_estimate` (ms) |
| Ticket Quality Checklist items | a real ClickUp checklist (only with `--checklist`) |
| `## Implementation notes …` | never sent |
| the metadata table itself | never sent — every row is already a field |

Two custom fields are filled automatically when the list has them: a number field named
`Time Estimate (h)` and a `users` field named `Assignee`. Those shadow native fields, and a
ticket that fills only the native half reads as unestimated or unassigned in the board views
the team actually uses. Everything else needs an explicit `--custom-field "Name=Value"`;
dropdown values are matched by option name, and an unknown value is reported and skipped
rather than failing the push.

Custom fields are set **after** the task is created, one call each, so a rejected value
costs you that field and not the whole ticket.

## Options

| Flag | Meaning |
|---|---|
| `--file` | path to the ticket `.md` (required) |
| `--list` | target list id (required) |
| `--status` | exact status name; validated against the list before anything is created |
| `--assignee` | `me` (the token's owner) or a numeric ClickUp user id; repeatable. Prefer `me` — the skill is shared, so a hardcoded id assigns everyone's tickets to one person |
| `--tag` | tag name, repeatable |
| `--time-estimate` | hours, overriding the metadata row |
| `--custom-field` | `"Name=Value"`, repeatable |
| `--checklist` | also create the Ticket Quality Checklist |
| `--no-update-md` | do not write the new task id into the file's `\| **ID** \|` row |
| `--dry-run` | resolve and print, create nothing |

## Timeouts

Creating the checklist costs about one API call per item, so a full Ticket Quality Checklist
(16 items today) plus the create call runs past the 120-second foreground limit. When
`--checklist` is on, run the
push **in the background** (`run_in_background: true`) and report the URL when it finishes.
Without the checklist the push is a handful of calls and runs fine in the foreground.

## When something fails

- **HTTP 401** — a stale token. Run `token_setup.py --status`: it will name the file the
  dead token is in, and whether a working one is being shadowed by it.
- **`No CLICKUP_API_TOKEN found`** — there is no token anywhere. See **Storing a token**.
- **`'X' is not a status on this list`** — the script checked before creating, so nothing
  was made. Re-run `--inspect` and use a real status name.
- **`the list has no custom field named ...`** — a warning, not a failure; the task is still
  created without that field.
- **Task created, then a `WARN` about a field or the checklist** — the ticket exists and the
  URL is valid. Fix the field in ClickUp or re-run just that part; do not push the ticket
  again, or the list ends up with duplicates.
- **`No '## User Story' heading found`** — the file does not follow `ticket-format.md`. Fix
  the file, not the script.
