# ADR-0005: A habit tracker and mood log, with soft delete

- Status: accepted
- Date: 2026-10-08
- Deciders: Kathryn Chiew

## Context

The quotes table was a placeholder (ADR-0004). What I'd actually keep is
a record of the habits I do and how I feel. The two are more useful
together than apart: "am I happier on days I exercise?" can only be
answered if both live in one place.

That raised ADR-0004's open question: add delete? If so, hard or soft?

## Decision

Two tables, `habit_log` and `mood_log`, each with an optional detail
column and a nullable `deleted_at`. Five tools: `log_habit`, `log_mood`,
`show_history(days)`, `delete_entry(kind, id)`, `restore_entry(kind, id)`.

**Delete is soft.** `delete_entry` sets `deleted_at`; `show_history` hides
those rows; nothing is ever removed, and `restore_entry` clears it.

## The roads not taken, and why

**No delete at all** keeps the most honest record, but here the *model*
writes the entries from casual conversation. "I'm thinking about going
for a run" can become a logged run. Without a way to remove that, wrong
entries quietly corrupt streaks and patterns forever.

**Hard delete** fixes mistakes, but it also lets a mood log be edited
into a nicer story than the one that happened — ADR-0004's "the memory
lies about its own past." A deleted bad day should be *hidden*, not
erased. And an accidental delete would be permanent.

**One `entries` table with a `kind` column** would make the combined
timeline a plain `SELECT`, but habits and moods have different detail
fields (`note` vs `reason`), and two tables keep each one readable.
`show_history` does the combining with a `UNION ALL`.

**Streak and pattern tools** (`habit_streak`, `mood_by_habit`) were left
out for the same reason `search_quotes` was: the model can read
`show_history` and work these out itself at personal scale.

## Consequences

- Mistakes cost one tool call to undo, and an undo of the undo exists.
- The database grows forever, including hidden rows — fine at the scale
  of one person logging a few things a day.
- Server `instructions` tell the model to log only things actually done
  or felt and to report each entry's id, so a mistake is spotted and fixed
  in the same conversation it was made.
- The old `quotes` table (one test row) is left in the database
  untouched; no tool reads it anymore.
