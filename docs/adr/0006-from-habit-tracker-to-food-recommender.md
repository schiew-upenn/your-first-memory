# ADR-0006: From habit tracker to a Philly + NYC food recommender

- Status: accepted
- Date: 2026-10-29
- Deciders: Kathryn Chiew

## Context

The habit and mood log (ADR-0005) worked, but the question I actually
ask most is "where should I eat?" — and the answer depends on how I feel,
what I've been meaning to try, and what just opened. I split my time
between Philly and New York, and New York opens far more new places. A
model alone knows none of this: it has no memory of my moods or meals,
and its knowledge of restaurants stops at its training cutoff.

So the server keeps the mood log and gains three things: a list of
places, a log of meals, and a source of current restaurant news — for
two cities.

## Decision

**Two cities, and the city comes first.** Every place, meal, news query
and recommendation belongs to `philly` or `nyc`, and every tool requires
it (aliases like "Philadelphia" and "New York" are accepted). The server
`instructions` and the `my-ways` skill make "NYC or Philly?" the model's
first question in any food conversation, unless I've already named the
city. A missing or unknown city fails with a message telling the model
to ask.

**Three tables.** `mood_log` (unchanged from ADR-0005), `places` (city,
name, vibe, neighborhood, cuisine, want/tried, notes, link), and
`meal_log` (city, place, mood going in, rating 1–5, note). All keep soft
delete. Moods have no city: I feel the same wherever I am.

**News, read live, per city:**

| city | source | format | search | history |
|---|---|---|---|---|
| philly | Philly Mag (Foobooz) | RSS | `?s=` at the source | `?paged=` up to 5 pages |
| nyc | Eater NY | Atom | filtered locally | latest 10 (~1 day) |
| nyc | Grub Street (NY Mag) | RSS | filtered locally | latest 20 (~4 weeks) |

All are free, need no key, and are published to be read by programs.
Stories are flagged `[OPENING]` when the headline or the link reads like
an opening ("opens", "debut", "first look", Eater's `/restaurant-openings/`).

**Mood decides the vibe, and the vibe decides the shortlist.** Moods are
fixed to five (crying, sad, neutral, happy, ecstatic — the scale from
ADR-0005's skill, now enforced by the server). Places are tagged with one
of four vibes, and one table maps between them:

| mood | vibe |
|---|---|
| crying, sad | comfort |
| neutral | everyday |
| happy | new (want-to-try + recent openings) |
| ecstatic | splurge |

`recommend_for_mood(city, mood)` returns the vibe, the meals in that city
that went well (4–5/5) in that same mood before, the matching saved
places, and — for new or splurge — recent openings. The model picks from
that; it doesn't invent.

**Changed in place, not forked.** The habit tracker lives in git history;
`habit_log` stays in the database untouched, as `quotes` did in ADR-0005.

## The roads not taken, and why

**City as an optional parameter, defaulting to Philly.** Fewer questions,
but a wrong default silently gives Philly answers while I'm in Manhattan.
Required-and-asked is one extra exchange per conversation, and it's the
one I want.

**Remembering my last city.** Tempting, but where I am changes week to
week; a stale city is the same silent failure as a default.

**Google Places API** would add ratings, hours, and addresses in both
cities. Its free monthly allowance (since March 2025: per-SKU caps,
~1,000 calls on the Enterprise SKUs that carry ratings) easily covers one
person — but it needs a billing account with a card, and a leaked key or
a looping call costs real money. Deferred to its own ADR once this
version is deployed: one new tool, one new env var (ADR-0003).

**Yelp Fusion** has no lasting free tier anymore.

**NYT Dining's feed** works but is national food culture, not New York
openings. **The Infatuation and Time Out** have no working feed.

**Scraping restaurant pages or Instagram** breaks whenever the HTML
changes and sits badly with most sites' terms.

**Leaving the news to Claude's own web search.** It works on claude.ai,
but each answer comes from whatever pages the search returns. Fixed,
trusted sources give consistent answers with a link every time.

**Free-text vibes or moods with keyword matching** ("cozy", "soupy",
"wiped") read naturally but match unreliably — the six-value scale
ADR-0005's TESTS.md warned about. Fixed sets fail loudly at the tool
call, where the model can correct itself.

**A learned recommender** (scoring, embeddings) is out of scale. With a
few dozen meals, "what scored 4+ last time I felt this way" is the model,
and the LLM does the rest of the reasoning.

## Consequences

- A recommendation is only as good as the saved places: each city's list
  starts empty, so early answers lean on the news. Saving places as they
  come up is what makes it personal.
- NYC news only reaches back as far as its feeds hold (Eater NY about a
  day, Grub Street about four weeks) and can't search older stories;
  Philly can page back further. Asking regularly — or saving openings as
  they appear — is how NYC's list grows.
- Philly search reaches back to 2012, so news older than `max_age_days`
  (default 180; 60 for openings in recommendations) is dropped — old
  stories are often about places since closed.
- If a feed is down, news tools say so and recommendations still return
  saved places and past meals.
- Everything is still one shared log with no owner. Level 3's retrofit
  (`user_id` + Neon Auth) is what makes it mine alone.
