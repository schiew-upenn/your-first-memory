# your-first-memory

**A memory for a model that has none.** Sibling of
[`your-first-instrument`](https://github.com/jlumbroso/test-time-mcp-exercise):
last week your model got a sense of time; tonight it gets a record that
survives the end of the conversation.

Made mine: a **Philly + NYC food recommender that remembers how I feel**
(ADR-0006, which grew out of the habit and mood log of ADR-0005). It
asks "NYC or Philly?", checks how my last saved recommendation went,
then asks: recommendations, or new restaurants? New restaurants come
straight from the news (Philly Mag; Eater NY and Grub Street). A
recommendation comes after a few questions — mood, occasion, company,
cravings, dislikes, atmosphere, budget, where — as a one-line reading of
what I want, then three places with a fit chart showing why #1 wins
(ADR-0008). I rate the set: a miss asks what was wrong and adjusts, a
hit lets me put one on my try list, and it gets followed up next time
(ADR-0007).

Tools: `recommend_for_mood` · `present_recommendations` ·
`rate_recommendations` · `pending_followups` · `follow_up` · `food_news` ·
`save_place` · `list_places` · `log_meal` · `log_mood` · `show_history` ·
`delete_entry` · `restore_entry` — soft delete throughout, so a mistake
can be hidden but never truly lost.

- **In class**: follow [COURSE-STEPS.md](COURSE-STEPS.md).
- **Every design choice, with the road not taken**: [docs/adr/](docs/adr/) —
  four real decisions from the template, plus ADR-0005 to ADR-0008, my own.
- **Stack**: FastMCP (`mcp[cli] >=1.2,<2` — pinned, see render.yaml) +
  `psycopg` + [Neon](https://neon.tech) free-tier Postgres + Render
  free-tier compute. News feeds are read with the standard library —
  no API key, no new dependency. The secret (`DATABASE_URL`) lives only
  in the environment (ADR-0003).

*CAM · CIS 7000-008 · Penn · Fall 2026 — session 5 (2026-09-24).*
