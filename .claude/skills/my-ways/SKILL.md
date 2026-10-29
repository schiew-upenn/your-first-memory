---
name: my-ways
description: "How I like my Philly + NYC food recommender and mood log used. Use when I ask where to eat, want food recommendations, ask what's new or opening in Philly or New York, mention a restaurant I want to try, tell you about a meal I ate, say how I'm feeling, or ask about my week or past meals."
---

Every food conversation goes in this order. Ask ONE question at a time,
as a pop-up of choices above the chat box — your ask-the-user /
multiple-choice tool (AskUserQuestion in Claude Code) — using the options
the server gives, and always let me type my own answer. If I already
answered something, skip it. "Skip" is a fine answer.

## 1. City — always first

"NYC or Philly?" Skip it only if I already named the city.

## 2. Follow-ups from last time

Call pending_followups(city). For each place, ask: "Last time I recommended
X — did you go? How was it?" Record it with follow_up: "tried" with my 1–5
rating, "not_yet", or "not_going".

## 3. Recommendations or new restaurants?

"Are you looking for food recommendations, or for new restaurants in
<city>?"

- **New restaurants:** call food_news(city, openings_only=True) and give
  me the results as they are — date, name, link. No questions, no rating.
- **Recommendations:** go to step 4.

## 4. The questions (one at a time)

1. How are you feeling? → one of crying, sad, neutral, happy, ecstatic;
   log it with log_mood (map other words to the nearest, keep mine in
   the reason, and say which you picked).
2. What's the occasion? (weeknight dinner, date, celebration, catch-up…)
3. Are you with anyone — who? (solo, friends, a date, family, coworkers…)
4. Anything you're craving?
5. Anything you don't want to eat, or can't? (dislikes, allergies, diet)
6. What kind of restaurant mood? (cozy, lively, quiet, fancy, casual…)
7. Budget? ($, $$, $$$, or "treat myself")
8. Where and when? (neighborhood or how far you'll go; tonight or later;
   dine in or takeout)

## 5. Three recommendations, with a chart

Call recommend_for_mood with the city and every answer. Pick at least
THREE places that fit — none that missed earlier in this request. A place
that missed on an earlier day is fine again if today's answers avoid what
was wrong with it. If there aren't three good candidates, search the web
for current places you can link — never recommend from your own memory.

Score each place 0–5 against each of my answers, honestly, and call
present_recommendations with a one-line reading of what I really want.
Then reply in this order:

1. **The reading** — one italic line, before anything else.
2. **The fit chart** the tool returns, unchanged, in a code block.
3. **#1** — why it's the top pick, pointing at the rows where it wins.
4. **#2 and #3** — why each is a good relative match, and where it falls
   short of #1.
5. Links for all three, then: "How good are these recommendations, 1–5?"

## 6. My rating

Call rate_recommendations with the set number.

- **1–3:** ask what was wrong (if I didn't say) — too loud, too pricey,
  wrong food, too far? Don't re-ask the questions. Keep all my answers,
  change only what my feedback points to, tell me in one line how you're
  adjusting ("going quieter and cheaper"), and present three different
  places. Rate that set the same way.
- **4–5:** ask "Which one should I add to your try list?" with the three
  places as choices. save_place with that place's recommendation_id, so
  you'll ask me how it went next time.

## Always

Only log what I actually ate or actually feel — never plans or "maybe later."

After logging or saving, tell me in one line what you saved, with its
entry id so I can undo it.

Before deleting anything, say which entry and ask me first.

Before answering about my past, check my history — never guess.

If I'm just chatting or asking general food advice, do nothing and say nothing.
