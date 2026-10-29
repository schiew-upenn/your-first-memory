# ADR-0008: Three options, a one-line reading, and a fit chart

- Status: accepted
- Date: 2026-10-29
- Deciders: Kathryn Chiew

## Context

ADR-0007 gave ONE recommendation per round, so a rating was unambiguous.
In use, one place felt like a coin flip: I couldn't see *why* it won, or
what the runner-up would have been. I also wanted the model to show it
understood me before answering — after eight questions, a one-line read
of what I actually want is the check that it listened.

## Decision

**Before the places, a reading.** `present_recommendations` requires a
`reading`: one line, in the model's words, of what I want tonight
("Something warm and low-key with a friend — noodles over fuss, close by,
under $$"). It's shown first and stored with the set.

**At least three places, ranked by fit.** The model scores each place
0–5 against each answer I gave (skipped questions are left out). The
server — not the model — turns those into a fit % (points ÷ maximum),
ranks the places, and stores them as one set (`batch` = the top pick's
id, `rank`, `fit`). Fewer than three, or a missing score, is refused.

**A fit chart drawn by the server.** Rows are my answers ("Budget · $$"),
columns are the places, one █ per point, overall fit at the bottom. It's
monospace text, so it renders the same in Claude Code and the Claude app,
and it's the same chart every time because the server draws it.

**The reply has a fixed order:** reading → chart → why #1 wins (its best
rows) → why #2 and #3 are good relative matches and where they fall
short → links → "How good are these recommendations, 1–5?"

**The rating covers the set** (`rate_recommendations`). 4–5 → "Which one
should I add to your try list?" with the three as choices; the chosen
place is saved with its own recommendation id, so follow-ups (ADR-0007)
work per place. 1–3 → ask what was wrong, adjust, three *different*
places; the whole set is "missed" for this request.

## The roads not taken, and why

**Keep one recommendation (ADR-0007).** Cleaner rating, but no sense of
the trade-offs. Three ranked options with the reasons is how a friend
recommends: "X, but if you want quieter, Y."

**Let the model compute the percentages and draw the chart.** It works
until it doesn't — sums drift and the layout changes run to run. The
model judges fit (that needs language); the server does the arithmetic
and drawing (that needs consistency).

**A real chart image** (an artifact or a plotted PNG) looks nicer in the
Claude app but doesn't exist in Claude Code's terminal, and the server
can't render into the chat. Text bars work everywhere.

**Rate each of the three separately.** Three ratings per round is a
chore. One rating for the set, then "which one?", gets the same signal
with one extra tap.

## Consequences

- The scores are the model's judgment, not measurements. The chart makes
  that judgment visible and comparable — and arguable, which is the point.
- A miss now costs three places for this request, not one. That's
  intended: a "too pricey" miss usually applies to the whole set.
- Existing databases are upgraded in place (`ALTER TABLE … ADD COLUMN IF
  NOT EXISTS`); older single recommendations keep working for follow-ups.
- `record_recommendation` and `rate_recommendation` are replaced by
  `present_recommendations` and `rate_recommendations`.
