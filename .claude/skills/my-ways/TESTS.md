# Testing my-ways

Skills load at session start. **Run these in a NEW session**, one at a time,
typed as I'd actually type them. Don't read SKILL.md first in that session —
reading it contaminates the trigger test.

## 1. The rule that matters most — city first

> Where should I get dinner?

Pass: the first thing back is "NYC or Philly?" (mood may be asked in the
same message) — no tool called, nothing recommended yet.
Fail: any recommendation, news, or guessed city before I answer.

## 2. City already named — don't ask again

> I'm in such a good mood, what's good in New York tonight?

Pass: no city question; `log_mood("happy")` then
`recommend_for_mood("nyc", "happy")`; at most three places, each with a
reason, and a link for anything from the news.
Fail: asking "NYC or Philly?" anyway, or a restaurant no tool returned.

## 3. What's new

> What's opening lately?

Pass: "NYC or Philly?" first. After I answer, `food_news(city,
openings_only=True)`, each story with its date and link.

## 4. Ambiguous — a day, no feeling named

> Today was a lot. The interview went fine but I've been staring at the wall
> since I got home.

Pass: the feeling is read from my words and logged as one of
crying / sad / neutral / happy / ecstatic, my own words go in the reason,
and I'm told *which one was picked* so I can correct it. No city question —
this isn't about food.
Fail: asking me "how are you feeling?" instead of reading it.

## 5. A meal, then the loop closes

> Just had the pho at Pho 75 in Philly, honestly perfect. I was feeling pretty low before.

Pass: `log_meal("philly", "Pho 75", 5, "sad", ...)` with the rating read
from "perfect", and the meal id reported. Then in a NEW conversation,
"I'm sad, where should I eat in Philly?" should bring Pho 75 back as what
worked — and the same question for NYC should not.

## 6. Saving a place, city unknown

> My friend says Vetri is amazing for a birthday dinner.

Pass: "NYC or Philly?" (or a correct guess said out loud to confirm),
then an offer to save it as `splurge`.
Fail: logging a meal — I haven't eaten there.

## 7. The trap — a plan, not a thing done

> I'm thinking about getting ramen in the East Village tomorrow.

Pass: nothing logged. "Never plans" is the rule most likely to be broken,
because the sentence names food and a city.

## 8. Do nothing

> Is it bad to eat late at night?

Pass: a plain answer, nothing logged, no city question, no mention of
the log.

---

If the skill never fires on 1, 2 or 5, the **description** is the culprit,
not the body. Tune the description, new session, run all eight again.
