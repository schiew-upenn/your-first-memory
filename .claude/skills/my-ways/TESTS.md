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

## 6. One recommendation, then a rating

Pass: ONE place, why it fits my answers, a link, `record_recommendation`
called, and "How good is this recommendation, 1–5?"

## 7. A bad rating starts over

> 2, too loud

Pass: `rate_recommendation(id, 2, "too loud")`, then the whole sequence again
from the mood question; the next pick is a different place.

## 8. A good rating → try list

> 5

Pass: "Want me to add it to your try list?" → yes → `save_place(...,
recommendation_id=id)`.

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
