# write-ticket — how to use it

For the team. This is the human guide; the files next to it are for Claude.

The skill turns a description of some work into a backlog ticket, saves it as a
markdown file you review, and then — only after you say yes — creates the ClickUp task.

You do not have to read `SKILL.md`. Claude reads that.

---

## One-time setup

You need two things: Claude Code open in this repository, and a ClickUp token.

**The token.** Each person uses their own — it is a personal token, not a shared one. Get it
from ClickUp → **Settings → Apps → API Token**. It starts with `pk_`.

You do not have to set it up in advance. The first time you push a ticket, Claude checks for
a token and asks you for one if it is missing. If you would rather do it now:

```bash
cd .claude/skills/write-ticket/scripts
python token_setup.py --status
```

That tells you whether you already have a working token and where it is. To store one:

```bash
CLICKUP_TOKEN_INPUT=pk_your_token python token_setup.py --save --target user
```

`--target user` puts it in `~/.claude/clickup.env`, outside the repository. That is the
recommended place: the token is yours, the repository is shared, and a file outside the repo
cannot be committed by mistake. Use `--target repo-env` instead if you prefer it in the
repo-root `.env` next to the database settings.

The script checks the token against ClickUp before saving it, and refuses to write it
anywhere git would track. It never prints your token.

**Python.** The scripts need Python 3 and nothing else — no `pip install`. They use only the
standard library.

---

## Writing a ticket

Type `/write-ticket` and describe the work, or just describe the work and ask for a ticket.
Both reach the same place.

```
/write-ticket add an endpoint that returns the customer's saved addresses
```

```
we need a ticket for the bug where the cart total ignores the coupon after
the user changes the quantity
```

Then Claude does five things. You are involved in three of them.

**1. It asks you what it cannot work out.** Things like the business reason, who is allowed
to do the action, or a decision the code does not settle — for example whether a duplicate
should be rejected with `409` or accepted quietly. It asks these together, in one question,
with a suggested answer you can just accept. If your description already covers everything,
it skips this and says so.

**2. It reads the code.** The router, the handler, the service, the queries, the schema. This
is why the ticket names real routes and real columns instead of writing "the endpoint should
validate its input". Nothing is written yet.

**3. It writes the file** to `.claude/_specs/<name>.md` and tells you the path.

**4. It stops and waits for you.** Open the file and read it. Claude will point out anything
it had to guess — those are marked `⚠️` in the ticket. Tell it what to change, or say it
looks good.

**Nothing reaches ClickUp until you say yes.** If you never answer, no task is created.

**5. It pushes to ClickUp** and gives you the task link. Before creating anything it asks:

- **Which list?** It reads your ClickUp live and shows the real lists — the current sprint,
  Product Backlog, Bugs, Fixes & Technical Debt. It does not use a remembered sprint id,
  because those go stale the week a new sprint starts.
- **Do you want the Ticket Quality Checklist?** As a real ClickUp checklist on the task.
  This costs about one API call per item, so it is a per-ticket choice.

The task is assigned to you by default.

Afterwards the ClickUp task id is written back into the local file, so the two stay linked.

---

## Pushing a ticket you already wrote

If a `.claude/_specs/*.md` file already exists and you only want it in ClickUp:

```
push .claude/_specs/add-customer-addresses-endpoint.md to the current sprint
```

Claude skips straight to the push. There is no second review step — asking for it is your
approval.

---

## Things worth knowing

**The ticket files are not committed.** The repository's `.gitignore` has a `_specs/` rule
that also covers `.claude/_specs/`, so your ticket files stay on your machine. The ticket's
real home is ClickUp. Tell the team if you want this changed.

**The metadata table is not sent to ClickUp.** Title, Status, Assignee, Time Estimate and the
rest are real ClickUp fields already. Copying them into the description too would give you two
versions of the same value that slowly stop matching. The description starts at `## User
Story`.

**Implementation notes stay local.** If the ticket has a `## Implementation notes` section at
the end, it is never pushed. That section is for the developer who picks the ticket up — file
and line references, existing test helpers, known problems. Write freely in it.

**Statuses are different per list.** The backlog lists start at `draft`, the sprint lists at
`to do`. Claude reads the real list before pushing and maps it. Check the `Status :` line it
prints if you care which one it used.

---

## When something goes wrong

Run this first — it answers most questions:

```bash
cd .claude/skills/write-ticket/scripts
python token_setup.py --status
```

| Problem | What it means |
|---|---|
| `HTTP 401` | The token is dead or was rotated. `--status` names the file it is in. |
| `No CLICKUP_API_TOKEN found` | No token anywhere yet. See **One-time setup**. |
| A token is found but still 401 | An old token in a higher-priority file is hiding a good one. `--status` shows the order and marks which is effective. |
| `'X' is not a status on this list` | Nothing was created — the check runs before the task. Use a status the list really has. |
| The task was created but a field is missing | The task is fine and the link works. Fix the field in ClickUp. **Do not push again**, or you get two tasks. |
| The push seems to hang | A full checklist is about 17 API calls. Claude runs it in the background for this reason. |

Ask Claude to run the push with `--dry-run` if you want to see exactly what it would create
without creating it.

---

## What is in this folder

| File | Who reads it |
|---|---|
| `README.md` | you |
| `SKILL.md` | Claude — the five phases and the rules it follows |
| `references/ticket-format.md` | Claude — the ticket format: metadata, the 3 sections, the checklist |
| `references/clickup-push.md` | Claude — the push commands, field mapping, troubleshooting |
| `scripts/token_setup.py` | checks and stores your ClickUp token |
| `scripts/clickup_lists.py` | lists the real ClickUp destinations |
| `scripts/clickup_push.py` | creates the task from the markdown file |
| `scripts/clickup_api.py` | shared token loading and HTTP |

The ticket format lives in `references/ticket-format.md` and nowhere else. If the team changes
the standard, change it there — do not keep a second copy.
