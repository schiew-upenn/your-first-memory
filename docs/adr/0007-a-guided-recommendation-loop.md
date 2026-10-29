# ADR-0007: A guided recommendation loop, rated and followed up

- Status: accepted
- Date: 2026-10-29
- Deciders: Kathryn Chiew

## Context

ADR-0006 recommended from one input: my mood. But "where should I eat?"
depends on more — the occasion, who I'm with, what I'm craving, what I
won't eat, the atmosphere I want, budget, and where I am. And the server
never learned whether a recommendation was any good, or whether I went.

Two different questions were also mixed together: "pick a place for me"
and "what just opened?" The second needs no questions at all.

## Decision

**A fixed conversation order** (server `instructions` + `my-ways` skill):

1. "NYC or Philly?" (ADR-0006).
2. `pending_followups(city)` — ask how past saved recommendations went.
3. "Food recommendations, or new restaurants in <city>?" New restaurants
   → `food_news(openings_only=True)`, given as-is. Done.
4. Recommendations → one question per message: mood, occasion, company,
   cravings, don't-want, restaurant atmosphere, budget, where/when.
   Anything already answered is skipped.
5. ONE recommendation, recorded with `record_recommendation`, rated 1–5.
6. 1–3 → rejected, never suggested again, and the whole sequence starts
   over. 4–5 → offer the try list (`save_place(recommendation_id=…)`).
7. Next conversation in that city, step 2 asks how it went:
   `follow_up(tried | not_yet | not_going)`. "Tried" logs the meal.

**A `recommendations` table** holds the loop's state: place, mood, the
answers, reason, link, the rating, and a status that moves
`suggested → rejected | liked → saved → tried | skipped`.

**Candidates beyond the tools.** Saved places and news are too thin for
"quiet, no spice, with my parents" — so when nothing fits, the model may
use a web search for a current place it can link. Still never from memory:
restaurants close, and a link is how I check.

## The roads not taken, and why

**Three options per round** (ADR-0006's skill) — but then a rating is
ambiguous: which one was bad? One place, one rating, keeps the signal clean.

**All the questions in one message** is faster but reads like a form, and
answers get skipped. One at a time, with examples, and skipping what I
already said, keeps it a conversation.

**Restarting with my previous answers kept** would be quicker, but a bad
recommendation often means an answer was wrong ("actually I don't want
loud"). Asking again lets me change it.

**Following up on every recommendation**, liked or not — too much nagging.
Only places I chose to save are followed up; "not yet" waits a day
(`last_asked_at`), "not going" stops it.

**Server-side scoring of the answers** (filters on cuisine, price) would
need structured restaurant data I don't have (see Google Places, ADR-0006).
The model reasons over the answers; the server keeps the record.

## Consequences

- A recommendation now takes ~8 short exchanges. Saying several things
  up front ("happy, friend's birthday, NYC") skips those questions.
- Rejected places and their reasons accumulate per city and are shown to
  the model every time, so the same miss isn't repeated.
- Follow-ups only happen in a conversation about the same city, and only
  12+ hours after saving, so a place saved at lunch isn't asked about at
  dinner.
- The "ask in this order" behaviour lives in instructions and the skill;
  the server can't force it. The tools make each step easy and each
  result says what to do next.
