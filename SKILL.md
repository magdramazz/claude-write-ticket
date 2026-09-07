---
name: write-ticket
description: >-
  Write a backlog ticket (User Story + Acceptance Criteria + Test Cases) that follows
  the Backlog Ticket Standard, save it to .claude/_specs/<slug>.md, and — only after
  the user reads and accepts the file — push it to ClickUp with the bundled Python scripts,
  asking first which sprint, folder or backlog list it belongs in. Use this whenever the user
  asks for a ticket, task, user story, backlog item, work item, or spec; when they describe a
  feature, bug or piece of work and say "turn this into a ticket", "create a task for this",
  "write this up", or "put this in the sprint" — even if they never use the word "ticket";
  and also when they just want an existing .claude/_specs/*.md file pushed to ClickUp.
---

# Write Ticket — backlog ticket, then ClickUp

Two jobs, in a fixed order, with a human gate between them:

1. Turn a rough description into a ticket that satisfies the **Backlog Ticket
   Standard**, saved as a markdown file in `.claude/_specs/`.
2. After the user has read that file and said yes, push it to ClickUp.

The gate is the whole point. A ticket in ClickUp is visible to the team and gets picked up;
a file is cheap to rewrite. Never collapse the two steps, and never push a ticket the user
has not explicitly accepted — "looks good" or "push it" is acceptance, silence is not.

## The format is defined in one place — read it, do not invent it

`references/ticket-format.md` is canonical: the required metadata, the status workflow, the
exact 3-section body template, the Ticket Quality Checklist, and the common mistakes that
get tickets rejected.

Read it before writing any ticket, rather than working from memory. A ticket that drifts
from the format is sent back to its author to be rewritten, which is the expensive failure
mode this skill exists to avoid. You do not need it on the push-an-existing-file path,
which is why it is a separate file rather than part of this one.

## Context that shapes the criteria

The standard is project-neutral. These are the rules that make a ticket right:

- **Tenant isolation is real and mandatory.** The application is multi-tenant: every read and
  write must be scoped to the caller's tenant, and no tenant may ever read or mutate
  another's rows. The standard lists `Scope & Tenant Safety` as one section among several;
  it is never optional, and criteria that ignore scoping are the ones that turn into
  incidents.
- **API-first.** Most work items are backend endpoints. Authorization failures return an
  HTTP status (401 unauthenticated / 403 forbidden — derive which from how the route is
  registered), and validation failures return the structured JSON error envelope.
- **No UI surface means say so.** If the feature has no UI, write the UI half of
  `UI & API Consistency` as explicitly N/A. Inventing UI behavior for a JSON endpoint is
  worse than an admitted gap, because someone downstream will try to build it.
- **The Actors are** `System Admin`, `Account Admin`, `Normal User`, `System` — where
  `System` means a non-human caller: a RabbitMQ consumer, a cron job, the CI suite.

For the **Backbone**, take the module name from the "Modules (Backbones)" section of
`CLAUDE.md`. That list is maintained as the code changes, so it is the live one — do not
keep a second copy anywhere. If the work implies a module that does not exist yet, name it
clearly rather than forcing it into a neighbour.

---

## Phase 1 — Understand the request

The user gives you a description. It will be shorter than the standard needs — a one-line
description never contains authorization rules, tenant scoping, validation, or audit
behavior, yet the standard requires a section for each.

The useful split is: **derive what the repository can tell you, ask only what it cannot.**

Derive from the repo (do not ask):
- whether the route is public or protected → the auth failure code, and the whole
  Authorization section
- which module it belongs to → the Backbone
- what the request/response actually look like → Form Fields, Validation & Constraints
- what already exists → the in-scope / out-of-scope boundary

Ask the user (they are the only source):
- the business benefit — the "so that" half of the user story, when it is not obvious
- the Actor, when a new capability could belong to more than one role
- a genuine behavior fork the code does not settle (e.g. a duplicate → `409`, or an
  idempotent `200`?)
- the time estimate and the target sprint, when they matter
- anything the description says ambiguously ("should probably", "etc.", "handle errors")

Ask these in **one batch** with `AskUserQuestion`, and put a concrete recommendation first in
every option list so the user can confirm rather than compose. A ticket interview that
dribbles out one question per turn is worse than a slightly wrong assumption clearly flagged.

If the description is already precise, skip straight to Phase 2 and say so.

## Phase 2 — Ground the ticket in the real code

This is what separates a grounded ticket from a generic one. Before writing, find:
- the route registration in the router (public group or `protected`?)
- the handler → service → repository chain, and the queries in `db/queries/`
- the columns and constraints in the schema
- the existing tests or fixtures the implementer will reuse

Cite what you find by `file.go:line`. An acceptance criterion that names the real route,
the real column and the real error path is testable as written; "the endpoint validates its
input" is not, and it is exactly the wording the standard rejects.

When the investigation turns up something that is wrong today but is not this ticket's job
to fix, do not silently fold it in. State it under **Validation & Constraints** as behavior
the ticket *pins*, and note in the summary paragraph that each deserves its own ticket.
Quietly widening scope is how a 6-hour ticket becomes a 3-day one.

## Phase 3 — Write the file

Location `.claude/_specs/` — create the directory if it is missing. Filename is a kebab-case
slug of the Title (`add-cart-overview-endpoint.md`). If that filename exists and holds a
*different* ticket, add a short disambiguator instead of overwriting.

When one run produces several tickets — an epic split into children — write one file per
ticket and name them so the relationship survives the directory listing: `epic-<slug>.md`
alongside `<slug>-01-foundation.md`, `<slug>-02-….md`. Each child is a complete ticket in its
own right, and each references the epic by ID.

The file is metadata table → the 3 standard sections → the Ticket Quality Checklist, and
optionally implementation notes at the end.

**The metadata table shape is a parser contract** — `clickup_push.py` reads Title, Status
and Time Estimate out of these exact rows, so keep the `| **Key** | value |` form:

```markdown
# <Title>

| Property | Value |
|---|---|
| **Title** | Verb + Object |
| **ID** | _auto_ |
| **Status** | Backlog |
| **Backbone** | Cart |
| **Actor** | Normal User |
| **Assignee** | Magd Hammoud |
| **Time Estimate (h)** | 6 ⚠️ (estimate — reason) |
| **Sprint** | Sprint 5 ⚠️ (confirm before pushing) |
| **User Story Relation** | ⚠️ unknown — no Epic yet |
| **Estimation per User Story** | — |
```

Mark every value you had to guess with `⚠️` and a one-line reason. A blank required field
fails the standard; a flagged estimate is honest and gets corrected in seconds.

Two trailing sections, both handled deliberately by the push:

- **`## Ticket Quality Checklist`** — required in the file. Paste it from
  `references/ticket-format.md` **with its heading**, all of the items, ticking `[x]` only
  where the ticket genuinely satisfies the item. Leaving one `[ ]` with a reason is more
  useful than ticking every box. The heading is what the push script uses to know where the
  description ends, so a checklist pasted without it lands inside the ClickUp description as
  body text. (What is optional is only whether those items also become a *ClickUp* checklist
  — that is the user's per-push choice in Phase 5, not a choice about the file.)
- **`## Implementation notes (not part of the ticket body)`** — optional. Facts you gathered
  so the implementer does not rediscover them: file:line references, reusable fixtures, known
  mismatches. The push script never sends this section to ClickUp, so write it freely.

Tell the user the path when you are done.

## Phase 4 — The acceptance gate

Tell the user the file is ready, give the path, and give a short summary of the decisions
you made and the `⚠️` items you want them to check. Then stop and ask whether they have
read it and accept it.

If they want changes, edit the file and ask again. Do not proceed to Phase 5 on anything
short of a clear yes.

## Phase 5 — Push to ClickUp

Read `references/clickup-push.md` before running anything — it has the exact commands, the
field mapping, and what to do when a call fails.

The shape of this phase:

0. **Check the token first.** Run `token_setup.py --status`. It is one API call, it prints
   no secret, and it distinguishes the two failures that look identical from the outside: no
   token at all, versus a token that is found but dead. Doing this before the destination
   walk means a credential problem surfaces in two seconds rather than after the user has
   picked a sprint. If it reports a working effective token, say nothing and move on.

   When there is no working token, ask the user for one — see **Getting a token** below.

1. **Show real destinations.** Run `clickup_lists.py` (optionally with a `--space` argument
   to narrow to a project). Sprint lists are created and closed constantly, so a remembered
   list id is wrong the week the next sprint opens — and a ticket in last sprint's list is
   invisible until someone goes looking. Offer the live options with `AskUserQuestion`
   (current sprint, Product Backlog, Bugs, Fixes & Technical Debt), and let the user name
   any other list.
2. **Inspect the chosen list** with `clickup_lists.py --inspect <list_id>` to learn its real
   statuses and custom fields. Backlog lists start at `draft`; sprint lists start at
   `to do`. An explicit `--status` that the list does not have is refused locally, before
   anything is created — but a *guessed* one is not refused, it is silently mapped, and an
   unmappable value falls back to the list's first status. Read the `Status :` line the push
   prints rather than assuming it took what the ticket said.
3. **Ask about the checklist.** The user decides per ticket whether the Ticket Quality
   Checklist items are created as a real ClickUp checklist. It costs roughly one API call
   per item, which is why the answer matters.
4. **Dry-run, then push.** `--dry-run` resolves everything and creates nothing — two
   read-only calls that catch a wrong list or status before a task exists in front of the
   team. Show its output, then run the real push.
5. **Report the URL.** The script also writes the new task id back into the `| **ID** |`
   row of the local file, so the spec and the ClickUp task stay linked.

### Getting a token

Only when `--status` shows none working. Two questions, in this order.

**Where should it live?** Ask with `AskUserQuestion`, and lead with the recommendation:

- **`user`** → `~/.claude/clickup.env`, outside the repository entirely. Recommend this
  first. A ClickUp personal token is tied to one person, and the repo is shared — a
  per-person credential does not belong in a shared working tree even a git-ignored one,
  because it travels with any copy of the directory.
- **`repo-env`** → the repo-root `.env`, next to the app config. Convenient when someone is
  already editing `.env` for the database, and it is what this machine uses today.
- **`claude-env`** → `.claude/.env`, git-ignored too, keeping ClickUp out of the app config.

**How should they supply it?** Two honest options — say which you recommend and why:

- **They add it themselves** (recommended). Give them the exact line to paste into the file
  they chose, `CLICKUP_API_TOKEN=pk_...`, then re-run `token_setup.py --status` to confirm.
  The token never enters this conversation.
- **They paste it here** and you run the save. Faster, but say plainly first that a token
  pasted into chat is stored in the transcript, and that if the transcript is ever shared
  they should rotate it in ClickUp → Settings → Apps. Then:

  ```bash
  CLICKUP_TOKEN_INPUT=<the token> python token_setup.py --save --target <choice>
  ```

  The script takes it from the environment rather than an argument, verifies it against the
  API before writing, refuses any path git would track, and prints only a masked form.

Never put a token in a file the user did not choose, never echo one back, and never write
one into the ticket, a commit, or `env.example` — that file gets a placeholder only.

### Push defaults

Apply these unless the user says otherwise — they are the standing convention:

- `--assignee me` — the ticket goes to whoever the ClickUp token belongs to. Use `me`, not a
  number. This skill is shared across the team, and a hardcoded id would assign every
  teammate's tickets to one person, which nobody notices until the board looks wrong. Pass a
  numeric id only when the user names someone else.
- the metadata table's Time Estimate, picked up automatically

The ticket's `| **Assignee** |` row is a human name for the reader; it is not what ClickUp
uses. If the user wrote a name there that is not themselves, ask before overriding `me`.

The metadata table itself is **never** sent to ClickUp. Every row of it is already a real
ClickUp field — task name, status, assignee, tag, time estimate, custom fields — and a
second copy inside the description drifts out of sync with the field it duplicates. The
push starts at `## User Story` for exactly this reason.

## Pushing a file that already exists

If the user points at an existing `.claude/_specs/*.md` and just wants it in ClickUp, skip
Phases 1–3 and start at Phase 5. The acceptance gate is already satisfied by them asking.


