# Ticket format

The canonical format for a backlog ticket (User Story / Work Item). Read this in
Phase 3, before writing the file.

This was previously the team document `.claude/docs/backlog-ticket-standard.md`. It now
lives with the skill, which makes the skill self-contained and makes this file the single
source of the format. It is loaded on demand rather than inlined into `SKILL.md`, because
the push-an-existing-file path never needs it.

The format is strict for a reason worth keeping in mind while writing: a ticket that does
not follow it gets sent back to its author to be rewritten. Every rule below exists because
some ticket once failed review on it.

## Required metadata

All of these are filled at the top of the ticket. In ClickUp each is a real field, not
description text — the push maps them onto the task's name, status, assignees, tags,
`time_estimate` and list custom fields.

| Property | Type | Required | Description |
|---|---|---|---|
| **Title** | Text | yes | Short title, Verb + Object (e.g. "Create User") |
| **ID** | Auto | yes | Generated automatically; the push writes the real task id back here |
| **Status** | Status | yes | From the workflow below |
| **Backbone** | Select | yes | The module — take the live list from `CLAUDE.md`'s "Modules (Backbones)" section |
| **Actor** | Multi-select | yes | System Admin, Account Admin, Normal User, System |
| **Assignee** | Person | yes | The responsible person |
| **Time Estimate (h)** | Number | yes | Estimate in hours |
| **Sprint** | Relation | no | Linked sprint |
| **User Story Relation** | Relation | no | Link to the Epic |
| **Estimation per User Story** | Relation | no | Extra estimates |

A blank required field fails review. When a value is genuinely unknowable — Assignee, exact
Sprint, Time Estimate — write a sensible placeholder and flag it `⚠️` with a one-line reason
rather than leaving it empty.

The table above documents the fields; it is **not** the shape you write into the ticket. In
the ticket file each field is a two-column row, `| **Key** | value |`, which is what
`clickup_push.py` parses. SKILL.md Phase 3 shows that shape — copy it from there.

### Status workflow

```
Backlog → Planned → TODO → In progress → Ready For Developer Review →
Ready For EM Review → EM Testing (DEV ENV) → Ready For Release →
In Release (STAGING) → Released To PROD
```

A new ticket is `Backlog`. Note that no ClickUp list actually has a status called `Backlog`
— the backlog lists start at `draft` and the sprint lists at `to do` — so the push maps it.
See `clickup-push.md`.

## Body — exactly 3 sections, in this order

```markdown
## User Story

As **a [Actor / role within a tenant]**,
I want to be able to **[action / capability]**,
so that **[business value / benefit]**.

[One short paragraph: scope, key constraints, what is in/out of scope,
references to related stories by ID.]

---

# Acceptance Criteria

## Scope & Tenant Safety
1. [Atomic, testable statement.]
2. [Atomic, testable statement.]

## Authorization
1. [Who may perform the action.]
2. Unauthorized attempts return 403 (API) / hide the control (UI).

## General Behavior
1. [What the feature does in general.]

## Form Fields

### Required Fields
1. **Field A**
2. **Field B**

Rules:
1. All required fields are validated before saving.

### Optional Fields
1. Field C
2. Field D

## Behavior After Saving
1. [What happens after a successful save.]

## Validation & Constraints
1. [Patterns, formats, mandatory-field enforcement.]

## UI & API Consistency
1. UI and API enforce identical rules.
2. Errors are returned in a structured format.

## Audit & Logging
1. [What is logged on success.]
2. [What is logged on failure.]

---

# Test Cases

## Happy Path — [Descriptive scenario name]
**Given** [precondition]
**And** [extra precondition]
**When** [action]
**Then**
- [Expected, observable result]
- [Expected, observable result]

---

## Validation Error — [Descriptive scenario name]
**Given** [precondition]
**When** [invalid action / invalid input]
**Then**
- [Validation error is shown]
- [No data is saved]

---

## Authorization Failure — [Descriptive scenario name]
**Given** [unauthorized user / role]
**When** [they attempt the action]
**Then**
- [UI hides the control]
- [API returns 403 Forbidden]
```

Two of the template's defaults are project-neutral and often wrong — resolve them
against the real code rather than copying the template: the auth failure code (401 for
unauthenticated, 403 for forbidden — read the route registration), and the UI half of
`UI & API Consistency`, which is explicitly N/A on a JSON-only endpoint.

## Ticket Quality Checklist

Paste this into the ticket **including its `## Ticket Quality Checklist` heading**, ticking
`[x]` only where the ticket genuinely satisfies the item. In ClickUp the items become a real
checklist (Task → Add Checklist → Paste by hand, or `--checklist` on the push).

The heading is a parser contract, not decoration. `clickup_push.py` uses it twice: it is
where the pushed description **stops**, and it is the only place checklist items are read
from. Omit it and the push silently does two wrong things at once — zero checklist items,
and all sixteen lines pasted into the task description as body text.

```markdown
## Ticket Quality Checklist

- [ ] Title is short and action-oriented (verb + object)
- [ ] Status, Backbone, Actor, Assignee, Time Estimate are filled
- [ ] Body contains all 3 sections: User Story, Acceptance Criteria, Test Cases
- [ ] User Story uses As / I want / so that format with a real benefit
- [ ] Summary paragraph includes scope, constraints, in/out of scope
- [ ] Acceptance Criteria are grouped into named sub-sections
- [ ] Every criterion is atomic and testable (yes/no)
- [ ] Tenant safety is explicitly addressed
- [ ] Authorization rules are clearly defined
- [ ] Validation rules are clearly defined
- [ ] Behavior After Saving is defined
- [ ] UI & API consistency is defined
- [ ] Audit & Logging rules are included
- [ ] Test Cases cover: Happy Path, Validation Error, Authorization Failure
- [ ] No ambiguous words ("maybe", "etc.", "should probably")
- [ ] Related tickets referenced by ID (if applicable)
```

Leaving one unticked with a reason is more useful than ticking all sixteen — an honest
`[ ] Related tickets referenced by ID — no Epic exists for test coverage yet` tells the
reviewer something; a full sweep of `[x]` tells them nothing.

## Common mistakes to avoid

**1. Bad titles.** Not vague nouns ("Tickets", "Users", "Orders") — action-oriented:
"Create User", "Edit Order", "Delete Ticket".

**2. Broken user-story format.** The "so that…" must state a benefit, not repeat the action.
All three clauses are required: As a…, I want…, so that….

**3. Weak acceptance criteria.** Not one long paragraph, not an unnumbered list, not
ungrouped. AC must be atomic, testable yes/no, and grouped into named sub-sections — and it
must include validation rules and authorization rules.

**4. Happy path only.** Validation errors and authorization failures are part of the
specification, not an afterthought.

**5. Missing or unstructured test cases.** All three kinds are required — Happy Path,
Validation Error, Authorization Failure — each in Given/When/Then form.

**6. Missing metadata.** No Assignee, no Time Estimate, no Actor, no Backbone: all of them
must be filled before the ticket is accepted.

**7. Ambiguous wording.** "maybe", "etc.", "should probably" are not testable. Replace each
with an explicit statement.

**8. No related tickets.** Link the parent Epic and related stories by ID.
