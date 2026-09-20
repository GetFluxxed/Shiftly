# Shiftly

The next release plan covers FastAPI, an installable mobile web app, and a
dedicated manager Inventory workspace with shelf information, camera counts,
partial weights, pars, shortage insights, and stretch barcode receiving. These
features are planned; the current capabilities are described below.

See the [implementation plan](docs/IMPLEMENTATION_PLAN.md),
[inventory specification](docs/INVENTORY.md), and [work packages](docs/TASKS.md).

Shiftly gives our team a simple, consistent way to communicate what happened
during each shift. Crewmembers can send notes from a phone or browser, and
managers can review those notes, understand the shape of the day, and keep the
team aligned without needing to be in the store.

## What Shiftly does

Shiftly turns everyday shift communication into a shared operational record.
Crewmembers submit concise notes about their shift, including what went well,
what needs attention, and anything the next person or manager should know.
Shiftly preserves the original notes and uses an AI briefing process to help
managers identify the most important information quickly.

The result is a faster, more reliable handoff between the store and its
managers, with less dependence on memory, scattered messages, or end-of-day
catch-up conversations.

## Built for two different perspectives

### Crew workspace

The crew workspace is intentionally lightweight and mobile-friendly so that
employees can submit a report from the store without a complicated workflow.
Crewmembers can:

- Sign in using their store's shared crew access.
- Identify themselves and select the relevant shift.
- Submit clear notes about the shift.
- Receive confirmation that the report was received.
- See the current store-wide Head's Up from management.
- See when the Head's Up was last updated.

Crewmembers send information upward to the manager. They do not see private
manager briefings or other employees' reports.

### Manager workspace

The manager workspace is designed for review and decision-making. Managers can:

- See reports from their assigned store.
- Open the most recent report automatically.
- Read the original crew notes alongside the generated briefing.
- Track whether a briefing is pending, processing, complete, or needs attention.
- Review an AI-generated Weekly Overview based on recent reports.
- Publish one current Head's Up message for the crew.
- Replace an outdated Head's Up without accumulating redundant messages.

Each manager has an individual account, while store data remains separated from
other stores.

## Four areas of the manager dashboard

The manager view brings the most useful information into one place:

1. **Shift Reports** - The incoming reports from crewmembers.
2. **Manager Briefing** - A concise briefing for the latest report.
3. **Weekly Overview** - An AI-assisted view of recurring wins, risks, and
   follow-up items from the past week.
4. **Head's Up** - The current message managers want the entire crew to see.

This layout separates the crew's original observations from the manager's
decision-support information while keeping both available during review.

## Why our team uses Shiftly

- **Faster manager review:** Important details are organized into briefings
  instead of requiring managers to read every note from scratch.
- **Better shift handoffs:** Reports create continuity between opening,
  mid-day, and closing teams.
- **More consistent communication:** Every employee follows the same basic
  reporting path, making patterns easier to recognize.
- **Clear accountability:** Reports are associated with the submitting
  crewmember and shift.
- **Store-wide alignment:** A current Head's Up gives management one visible
  place to share urgent context, priorities, or reminders.
- **Useful weekly perspective:** The Weekly Overview helps surface repeated
  issues and positive trends that may be missed in a single shift report.
- **Less manager travel and interruption:** Managers can stay informed without
  being physically present for every shift or relying on informal updates.
- **Mobile-first simplicity:** Crew members can complete the workflow quickly
  from an iPhone or any modern browser.

## Responsible AI assistance

Shiftly uses AI to support manager review, not to replace manager judgment.
The original employee notes remain available so managers can compare the
briefing with the source information and make their own decisions.

The briefing process is guided to focus on relevant shift information and to
reject empty, meaningless, repetitive, spam, or unrelated submissions.
Employee notes are treated as source material rather than instructions to the
AI system.

Briefings are saved with the exact notes used to create them. Managers can
therefore understand what information informed a briefing, even after the
report has been processed.

## Operational safeguards

Shiftly includes protections intended to keep the reporting workflow useful and
trustworthy:

- Empty and low-quality reports are rejected before they enter the reporting
  system.

  ## Starting a new workspace

  Shiftly does not require seeded store data to start. When the database is
  empty, the application can still start and display the sign-in page. A new
  authorized administrator can configure the server-side `ADMIN_SIGNUP_KEY` and
  select **Create a workspace** on the sign-in page to create:

  - The store name and store code.
  - The shared password used by crew members.
  - The first manager account and password.

  The first manager is signed in automatically after the workspace is created.
  Store codes and passwords should be unique, difficult to guess, and shared only
  with the intended team. The admin key is never stored in the database and must
  be supplied through the hosting provider's secret environment-variable system.
  The sign-up flow is rate-limited and creates the store, manager, and membership
  together so an incomplete workspace is not left behind if account creation
  fails.

  Additional manager account administration can be added separately without
  changing the crew reporting workflow or requiring seeded records.
- Exact duplicates and highly similar repeat reports are limited.
- Submission cooldowns, request limits, and size limits help prevent spam.
- Reports are stored before AI processing begins.
- Failed briefing jobs can be retried instead of silently disappearing.
- Managers only access reports belonging to stores where they are assigned.
- Crew and manager access use separate authenticated sessions.
- Crew access is shared at the store level, while manager access is individual.
- Credentials are stored as protected password hashes rather than exposed in
  the browser or in employee-facing pages.
- Store codes are protected and are not sent to the AI provider.

## The goal

Shiftly is meant to make shift communication routine, visible, and actionable.
Crewmembers get a quick way to report what matters. Managers get a dependable
record, focused briefings, and a clearer view of both today's operation and
the patterns developing across the week.
