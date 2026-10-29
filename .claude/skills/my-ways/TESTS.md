# Testing my-ways

Skills load at session start. **Run these in a NEW session**, one at a time,
typed as I'd actually type them. Don't read SKILL.md first in that session —
reading it contaminates the trigger test.

## 1. City first

> Where should I get dinner?

Pass: the first thing back is "NYC or Philly?" — nothing else, no tool called.
Fail: any recommendation, news, or guessed city before I answer.

## 2. Then the fork

> (answer to 1:) Philly

Pass: `pending_followups("philly")` is called, then "Are you looking for food
recommendations, or for new restaurants in Philly?"

## 3. New restaurants — no questions

> New restaurants

Pass: `food_news("philly", openings_only=True)`, results as they are (date,
name, link). No mood question, no rating.

## 4. Recommendations — one question at a time

> (new session) Philly. Recommendations.

Pass: mood, occasion, who I'm with, cravings, don't-want, restaurant mood,
budget, where/when — ONE per message, each with example answers. The mood
is logged as one of the five.
Fail: all questions dumped in one message, or a recommendation before
they're asked.

## 5. Skips what I already said

> I'm so happy, it's my friend's birthday, where should I eat in NYC?

Pass: no city, mood, occasion or who-with question — it goes straight to
cravings.

## 6. A reading, three places, a chart, then a rating

Pass, in this order: one italic line reading what I want; the fit chart
from `present_recommendations` in a code block; why #1 is the top pick
(pointing at its winning rows); why #2 and #3 are good relative matches
and where they fall short; links; "How good are these recommendations, 1–5?"
Fail: fewer than three places, no reading, a chart Claude drew itself, or
a place no tool or search returned.

## 7. A bad rating adjusts — it doesn't start over

> 2

Pass: "What was wrong with these?" → "too loud" →
`rate_recommendations(set, 2, "too loud")`, one line on how it's adjusting
("going quieter"), and three different, quieter places — with NO questions
re-asked.
Fail: going back to "How are you feeling?", or the same places again.

## 7b. A miss isn't forever

A place I rated 2 on an earlier day can come back when today's answers
avoid what was wrong (e.g. it was "too loud" for a date, today I want lively).

## 8. A good rating → try list

> 5

Pass: "Which one should I add to your try list?" with the three places as
choices → `save_place(..., recommendation_id=<that place's id>)`.

## 9. The follow-up (next day, NEW session)

> Philly

Pass: right after the city, "Last time I recommended X — did you go? How
was it?" → "yes, 4/5, great pasta" → `follow_up(id, "tried", 4, ...)`.
"Not yet" → `follow_up(id, "not_yet")`, asked again another day.

## 10. The trap — a plan, not a thing done

> I'm thinking about getting ramen tomorrow.

Pass: nothing logged.

## 11. Do nothing

> Is it bad to eat late at night?

Pass: a plain answer, nothing logged, no city question.

---

If the skill never fires on 1 or 5, the **description** is the culprit,
not the body. Tune the description, new session, run them again.
