"""your-first-memory — a Philly + NYC food recommender that remembers how you feel.

Ask a model "where should I eat tonight?" and it can only guess: it
doesn't know what just opened in Philly or New York, which places you've
been meaning to try, or that pho fixed your last bad day. This server
keeps those three things — your moods, your places, your meals — and
reads each city's restaurant news, so the model can recommend from a
*record* instead. See docs/adr/ for every choice made here; ADR-0006
covers the turn from habit tracker to food recommender.
"""
import html
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from mcp.server.fastmcp import FastMCP

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")

mcp = FastMCP(
    "your-first-memory",
    instructions=(
        "A food recommender for two cities, Philly and NYC, with a memory. "
        "Every food conversation follows this order (ADR-0007). "
        "1) FIRST question: 'NYC or Philly?' — unless the user already named "
        "the city. "
        "2) Call pending_followups(city). For each place the user saved from "
        "a past recommendation, ask whether they went and how it was, and "
        "record the answer with follow_up. "
        "3) Ask: 'Are you looking for food recommendations, or for new "
        "restaurants in <city>?' New restaurants: call food_news(city, "
        "openings_only=True) and give the results as they are — no questions. "
        "4) Recommendations: ask one short question at a time — mood, "
        "occasion, who they're with, cravings, anything they don't want to "
        "eat, the restaurant atmosphere they want, budget, and where/when — "
        "skipping anything already answered. Log the mood (one of crying, "
        "sad, neutral, happy, ecstatic) with log_mood, then call "
        "recommend_for_mood. "
        "5) Give ONE recommendation that fits every answer, record it with "
        "record_recommendation, and ask the user to rate it 1-5. "
        "6) rate_recommendation: 1-3 means start the whole question sequence "
        "again and never suggest that place again; 4-5 means ask whether to "
        "add it to their try list (save_place with recommendation_id). "
        "Only recommend places from the tools or from a web search you can "
        "link — never from memory. Only call log_meal for a meal the user "
        "actually ate. Tell them what you saved, with its entry id, so a "
        "mistake can be undone with delete_entry."
    ),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
)

# Soft delete (ADR-0005): deleted_at hides a row; it is never removed, so
# restore_entry can bring it back. habit_log (ADR-0005) is left in the
# database untouched; no tool reads it anymore (ADR-0006).
SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_log (
    id         SERIAL PRIMARY KEY,
    mood       TEXT NOT NULL,
    reason     TEXT,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS places (
    id           SERIAL PRIMARY KEY,
    city         TEXT NOT NULL,                -- one of CITIES
    name         TEXT NOT NULL,
    vibe         TEXT NOT NULL,                -- one of VIBES
    neighborhood TEXT,
    cuisine      TEXT,
    status       TEXT NOT NULL DEFAULT 'want', -- 'want' or 'tried'
    notes        TEXT,
    link         TEXT,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS meal_log (
    id         SERIAL PRIMARY KEY,
    city       TEXT NOT NULL,
    place      TEXT NOT NULL,
    mood       TEXT,                           -- how the user felt going in
    rating     INTEGER NOT NULL,               -- 1..5
    note       TEXT,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
-- One row per recommendation given (ADR-0007). status moves
-- suggested -> rejected | liked -> saved -> tried | skipped.
CREATE TABLE IF NOT EXISTS recommendations (
    id            SERIAL PRIMARY KEY,
    city          TEXT NOT NULL,
    place         TEXT NOT NULL,
    mood          TEXT,
    answers       TEXT,                        -- the user's answers, summarized
    reason        TEXT,
    link          TEXT,
    rating        INTEGER,                     -- 1..5: was it a good recommendation?
    comment       TEXT,
    status        TEXT NOT NULL DEFAULT 'suggested',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_asked_at TIMESTAMPTZ,                 -- last follow-up the user answered "not yet"
    deleted_at    TIMESTAMPTZ
);
"""

# The mood -> vibe mapping is the whole recommender (ADR-0006). Change it
# here and every recommendation follows.
MOODS = ("crying", "sad", "neutral", "happy", "ecstatic")
MOOD_VIBE = {
    "crying": "comfort",
    "sad": "comfort",
    "neutral": "everyday",
    "happy": "new",
    "ecstatic": "splurge",
}
VIBES = {
    "comfort": "warm, cozy, low-effort food — soup, noodles, a reliable takeout",
    "everyday": "your dependable favorites, nothing to decide",
    "new": "somewhere you haven't been — a new opening or a want-to-try",
    "splurge": "a celebration: the special-occasion spot",
}

# kind -> table. Table names can't be SQL parameters, so only these fixed
# strings ever reach the query text.
TABLES = {
    "mood": "mood_log",
    "place": "places",
    "meal": "meal_log",
    "recommendation": "recommendations",
}
KINDS = '"mood", "meal", "place", or "recommendation"'

# Each city's news (ADR-0006). Philly Mag is WordPress RSS with its own
# ?s= search and ?paged= history; Eater NY (Atom, latest 10) and Grub
# Street (RSS, latest 20) have neither, so NYC is searched locally.
CITIES = {"philly": "Philadelphia", "nyc": "New York City"}
CITY_ALIASES = {
    "philly": "philly", "philadelphia": "philly", "phl": "philly",
    "nyc": "nyc", "ny": "nyc", "new york": "nyc", "new york city": "nyc",
}
FEEDS = {
    "philly": [("Philly Mag", "https://www.phillymag.com/restaurants/feed/", True)],
    "nyc": [
        ("Eater NY", "https://ny.eater.com/rss/index.xml", False),
        ("Grub Street", "https://feeds.feedburner.com/nymag/grubstreet", False),
    ],
}
ATOM = "{http://www.w3.org/2005/Atom}"
OPENING = re.compile(
    r"\b(opens?|openings?|opened|debuts?|set to open|now open|coming soon|first look)\b",
    re.I,
)


def city_key(city: str) -> str | None:
    return CITY_ALIASES.get(city.strip().lower())


CITY_ERROR = 'city must be "philly" or "nyc" — ask the user: NYC or Philly?'


def db():
    """One connection per tool call (ADR-0002): Neon's free tier suspends
    when idle, and a fresh connection wakes it transparently. A held pool
    would die during the nap and greet you with a stale-connection error."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Not an error in the code — a feature "
            "waiting for setup: create a free database at neon.tech, copy the "
            "connection string, and set it as an environment variable "
            "(COURSE-STEPS.md, step 2)."
        )
    conn = psycopg.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
    return conn


def clean(text: str) -> str:
    return re.sub(r"<[^>]+>|\s+", " ", html.unescape(text or "")).strip()


def read_feed(source: str, url: str) -> list[dict]:
    """One feed, RSS or Atom, as a list of stories."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "your-first-memory/0.1 (personal MCP server)"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for it in root.iter("item"):
        items.append({
            "title": clean(it.findtext("title")),
            "link": (it.findtext("link") or "").strip(),
            "date": parsedate_to_datetime(it.findtext("pubDate")).date(),
            "summary": clean(it.findtext("description"))[:200],
        })
    for e in root.iter(ATOM + "entry"):
        link = e.find(ATOM + "link")
        items.append({
            "title": clean(e.findtext(ATOM + "title")),
            "link": link.get("href", "") if link is not None else "",
            "date": datetime.fromisoformat(e.findtext(ATOM + "published")).date(),
            "summary": clean(e.findtext(ATOM + "summary"))[:200],
        })
    for i in items:
        i["source"] = source
        # The link counts too: Eater NY files its weekly openings roundup
        # under /restaurant-openings/ with a headline that never says "open".
        i["opening"] = bool(OPENING.search(i["title"] + " " + i["link"]))
    return items


def fetch_news(city: str, search: str = "", pages: int = 1) -> list[dict]:
    """A city's stories, newest first. Searchable feeds are searched (and
    paged) at the source; the rest are filtered here on title + summary."""
    items = []
    for source, url, searchable in FEEDS[city]:
        if searchable:
            for page in range(1, max(1, min(pages, 5)) + 1):
                params = {"paged": page} if page > 1 else {}
                if search:
                    params["s"] = search
                items += read_feed(source, url + ("?" + urllib.parse.urlencode(params) if params else ""))
        else:
            found = read_feed(source, url)
            if search:
                words = search.lower().split()
                found = [i for i in found if all(w in (i["title"] + " " + i["summary"]).lower() for w in words)]
            items += found
    return sorted(items, key=lambda i: i["date"], reverse=True)


def recent(items: list[dict], max_age_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=max_age_days)
    return [i for i in items if i["date"] >= cutoff]


def format_news(items: list[dict]) -> str:
    return "\n".join(
        f"{i['date']}  {'[OPENING] ' if i['opening'] else ''}{i['title']} ({i['source']})\n"
        f"    {i['summary']}\n    {i['link']}"
        for i in items
    )


@mcp.tool()
def food_news(
    city: str, search: str = "", openings_only: bool = False, pages: int = 1, max_age_days: int = 180
) -> str:
    """Recent restaurant news for a city — "philly" (Philly Mag) or "nyc"
    (Eater NY + Grub Street): openings, reviews, dishes. If the user hasn't
    said which city, ask "NYC or Philly?" first. `search` narrows it
    ("ramen", "Fishtown", "opening"). `openings_only` keeps only stories
    whose headline is about a place opening. `pages` (max 5) goes further
    back, Philly only — NYC feeds hold only their latest stories (about a
    day for Eater NY, a few weeks for Grub Street). Stories older than
    `max_age_days` are dropped: old news is often about places since
    closed. Always give the user the article link."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    try:
        items = fetch_news(key, search, pages)
    except Exception as e:
        return f"Couldn't reach the {CITIES[key]} news feeds right now ({e}). Try again shortly."
    items = recent(items, max_age_days)
    if openings_only:
        items = [i for i in items if i["opening"]]
    if not items:
        return "No matching stories. Try a broader search" + (" or more pages." if key == "philly" else ".")
    return format_news(items)


@mcp.tool()
def log_mood(mood: str, reason: str = "") -> str:
    """Record how the user feels right now: one of crying, sad, neutral,
    happy, ecstatic. Map other words to the nearest and keep the user's own
    word in `reason`."""
    mood = mood.strip().lower()
    if mood not in MOODS:
        return f"mood must be one of {', '.join(MOODS)}; put the user's own word in reason."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mood_log (mood, reason) VALUES (%s, %s) RETURNING id, logged_at",
            (mood, reason or None),
        )
        mid, ts = cur.fetchone()
        conn.commit()
    return f"Logged mood #{mid} ({mood}) at {ts.isoformat()}."


@mcp.tool()
def save_place(
    city: str,
    name: str,
    vibe: str,
    neighborhood: str = "",
    cuisine: str = "",
    status: str = "want",
    notes: str = "",
    link: str = "",
    recommendation_id: int = 0,
) -> str:
    """Save a restaurant to the user's list for a city ("philly" or "nyc").
    `vibe` is what it's for: comfort, everyday, new, or splurge. `status`
    is "want" (to try) or "tried". `link` is where it came from, e.g. a
    food_news article. Pass `recommendation_id` when saving a place the
    user rated well, so they're asked how it went next time."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    vibe, status = vibe.strip().lower(), status.strip().lower()
    if vibe not in VIBES:
        return f"vibe must be one of {', '.join(VIBES)}."
    if status not in ("want", "tried"):
        return 'status must be "want" or "tried".'
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO places (city, name, vibe, neighborhood, cuisine, status, notes, link)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (key, name.strip(), vibe, neighborhood or None, cuisine or None, status,
             notes or None, link or None),
        )
        pid = cur.fetchone()[0]
        if recommendation_id:
            cur.execute(
                "UPDATE recommendations SET status = 'saved' WHERE id = %s AND deleted_at IS NULL",
                (recommendation_id,),
            )
        conn.commit()
    followup = " I'll ask how it went next time." if recommendation_id else ""
    return f"Saved place #{pid}: {name} ({key}, {vibe}, {status}).{followup}"


@mcp.tool()
def list_places(city: str, vibe: str = "", status: str = "") -> str:
    """The user's saved places in a city ("philly" or "nyc"), optionally
    filtered by vibe (comfort, everyday, new, splurge) and/or status
    ("want" or "tried")."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    query = "SELECT id, name, vibe, neighborhood, cuisine, status, notes FROM places WHERE deleted_at IS NULL AND city = %s"
    args = [key]
    if vibe:
        query += " AND vibe = %s"
        args.append(vibe.strip().lower())
    if status:
        query += " AND status = %s"
        args.append(status.strip().lower())
    with db() as conn, conn.cursor() as cur:
        cur.execute(query + " ORDER BY name", args)
        rows = cur.fetchall()
    if not rows:
        return f"No saved {CITIES[key]} places match."
    return "\n".join(
        f"#{pid} {name} — {v}, {st}"
        + "".join(f"; {x}" for x in (hood, cuisine, notes) if x)
        for pid, name, v, hood, cuisine, st, notes in rows
    )


@mcp.tool()
def log_meal(city: str, place: str, rating: int, mood: str = "", note: str = "") -> str:
    """Record a meal the user actually ate: which city ("philly" or "nyc"),
    where, how good (1-5), and how they felt going in (one of the five
    moods, optional). A saved place with the same name is marked "tried"."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    if not 1 <= rating <= 5:
        return "rating must be 1 to 5."
    mood = mood.strip().lower()
    if mood and mood not in MOODS:
        return f"mood must be one of {', '.join(MOODS)}."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meal_log (city, place, mood, rating, note) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (key, place.strip(), mood or None, rating, note or None),
        )
        mid = cur.fetchone()[0]
        cur.execute(
            """UPDATE places SET status = 'tried'
                WHERE city = %s AND lower(name) = lower(%s) AND deleted_at IS NULL""",
            (key, place.strip()),
        )
        conn.commit()
    return f"Logged meal #{mid}: {place} ({key}), {rating}/5."


@mcp.tool()
def recommend_for_mood(city: str, mood: str, craving: str = "") -> str:
    """Everything needed to recommend a meal in a city ("philly" or "nyc")
    for a mood (crying, sad, neutral, happy, ecstatic): what the mood calls
    for, past meals there that went well in this mood, matching saved
    places, places already rejected (never suggest these again), news
    matching `craving` (e.g. "ramen", "pizza"), and — for happy or
    ecstatic — recent openings. Choose ONE place that fits all the user's
    answers. If nothing here fits, search the web for a current place you
    can link; never recommend from memory."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    mood = mood.strip().lower()
    if mood not in MOODS:
        return f"mood must be one of {', '.join(MOODS)}."
    vibe = MOOD_VIBE[mood]
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT place, rating, comment FROM recommendations
                WHERE deleted_at IS NULL AND city = %s AND status = 'rejected'
                ORDER BY created_at DESC LIMIT 20""",
            (key,),
        )
        rejected = cur.fetchall()
        cur.execute(
            """SELECT place, rating, note FROM meal_log
                WHERE deleted_at IS NULL AND city = %s AND mood = %s AND rating >= 4
                ORDER BY logged_at DESC LIMIT 5""",
            (key, mood),
        )
        worked = cur.fetchall()
        cur.execute(
            """SELECT name, status, neighborhood, cuisine, notes FROM places
                WHERE deleted_at IS NULL AND city = %s AND vibe = %s
                ORDER BY status = 'want' DESC, name""",
            (key, vibe),
        )
        places = cur.fetchall()
    out = [f"{CITIES[key]} · mood: {mood} → vibe: {vibe} ({VIBES[vibe]})."]
    out.append("\nWhat worked before in this mood:")
    out += [f"  {p} — {r}/5" + (f"; {n}" if n else "") for p, r, n in worked] or ["  (no meals logged in this mood here yet)"]
    out.append(f"\nSaved {vibe} places:")
    out += [
        f"  {name} ({st})" + "".join(f"; {x}" for x in (hood, cuisine, notes) if x)
        for name, st, hood, cuisine, notes in places
    ] or [f"  (none saved yet — save_place with city={key}, vibe={vibe})"]
    if rejected:
        out.append("\nAlready rejected — don't suggest again:")
        out += [f"  {p} — rated {r}/5" + (f"; {c}" if c else "") for p, r, c in rejected]
    if craving:
        out.append(f"\n{CITIES[key]} news matching \"{craving}\":")
        try:
            found = recent(fetch_news(key, craving), 365)[:5]
            out.append(format_news(found) if found else "  (nothing recent — try a web search)")
        except Exception as e:
            out.append(f"  (news feeds unreachable: {e})")
    if vibe in ("new", "splurge"):
        out.append(f"\nRecent {CITIES[key]} openings:")
        try:
            news = fetch_news(key, "open", 2) if key == "philly" else fetch_news(key)
            openings = [i for i in recent(news, 60) if i["opening"]][:6]
            out.append(format_news(openings) if openings else "  (none in the latest stories)")
        except Exception as e:
            out.append(f"  (news feeds unreachable: {e})")
    return "\n".join(out)


@mcp.tool()
def record_recommendation(
    city: str, place: str, mood: str, answers: str, reason: str, link: str = ""
) -> str:
    """Record the ONE recommendation you're about to give, before asking
    the user to rate it. `answers` summarizes what they told you (occasion,
    company, cravings, dislikes, atmosphere, budget, where/when); `reason`
    is why this place fits; `link` is the article or page it came from."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    mood = mood.strip().lower()
    if mood and mood not in MOODS:
        return f"mood must be one of {', '.join(MOODS)}."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO recommendations (city, place, mood, answers, reason, link)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (key, place.strip(), mood or None, answers or None, reason or None, link or None),
        )
        rid = cur.fetchone()[0]
        conn.commit()
    return f"Recorded recommendation #{rid}: {place}. Now ask the user to rate it 1-5."


@mcp.tool()
def rate_recommendation(recommendation_id: int, rating: int, comment: str = "") -> str:
    """The user's 1-5 rating of a recommendation (is it a good fit?).
    `comment` is what they said about why. Returns what to do next."""
    if not 1 <= rating <= 5:
        return "rating must be 1 to 5."
    status = "liked" if rating >= 4 else "rejected"
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE recommendations SET rating = %s, comment = %s, status = %s
                WHERE id = %s AND deleted_at IS NULL RETURNING place, city""",
            (rating, comment or None, status, recommendation_id),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return f"No recommendation #{recommendation_id}."
    place, city = row
    if status == "liked":
        return (
            f"{place} rated {rating}/5 — a good recommendation. Ask whether to add it "
            f"to their try list: save_place(city=\"{city}\", ..., recommendation_id={recommendation_id})."
        )
    return (
        f"{place} rated {rating}/5 — not a good fit, and it won't be suggested again. "
        "Ask briefly what missed if they haven't said, then start the whole question "
        "sequence again from the mood question."
    )


@mcp.tool()
def pending_followups(city: str) -> str:
    """Places the user saved from a past recommendation in this city and
    hasn't reported on yet. Call right after learning the city; for each,
    ask whether they went and how it was, then call follow_up."""
    key = city_key(city)
    if not key:
        return CITY_ERROR
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, place, created_at FROM recommendations
                WHERE deleted_at IS NULL AND city = %s AND status = 'saved'
                  AND coalesce(last_asked_at, created_at) < now() - interval '12 hours'
                ORDER BY created_at""",
            (key,),
        )
        rows = cur.fetchall()
    if not rows:
        return "No follow-ups pending."
    return "Ask about each:\n" + "\n".join(
        f"  recommendation #{rid}: {place} (recommended {ts:%b %d})" for rid, place, ts in rows
    )


@mcp.tool()
def follow_up(recommendation_id: int, outcome: str, rating: int = 0, note: str = "") -> str:
    """Record how a saved recommendation turned out. `outcome` is "tried"
    (they went — give `rating` 1-5 for the meal), "not_yet" (ask again
    another day), or "not_going" (stop asking)."""
    outcome = outcome.strip().lower()
    if outcome not in ("tried", "not_yet", "not_going"):
        return 'outcome must be "tried", "not_yet", or "not_going".'
    if outcome == "tried" and not 1 <= rating <= 5:
        return "For a place they tried, rating must be 1 to 5."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT city, place, mood FROM recommendations WHERE id = %s AND deleted_at IS NULL",
            (recommendation_id,),
        )
        row = cur.fetchone()
        if not row:
            return f"No recommendation #{recommendation_id}."
        city, place, mood = row
        if outcome == "not_yet":
            cur.execute("UPDATE recommendations SET last_asked_at = now() WHERE id = %s", (recommendation_id,))
            conn.commit()
            return f"OK — I'll ask about {place} again another day."
        if outcome == "not_going":
            cur.execute("UPDATE recommendations SET status = 'skipped' WHERE id = %s", (recommendation_id,))
            conn.commit()
            return f"OK — won't ask about {place} again."
        cur.execute("UPDATE recommendations SET status = 'tried' WHERE id = %s", (recommendation_id,))
        cur.execute(
            "INSERT INTO meal_log (city, place, mood, rating, note) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (city, place, mood, rating, note or None),
        )
        mid = cur.fetchone()[0]
        cur.execute(
            """UPDATE places SET status = 'tried'
                WHERE city = %s AND lower(name) = lower(%s) AND deleted_at IS NULL""",
            (city, place),
        )
        conn.commit()
    return f"Logged meal #{mid}: {place} ({city}), {rating}/5 — recommendation #{recommendation_id} closed."


@mcp.tool()
def show_history(days: int = 7) -> str:
    """Moods, meals, and recommendations (both cities) from the last `days`
    days, oldest first, on one timeline. Deleted entries are left out.
    Times are UTC."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 'mood', id, mood, reason, logged_at FROM mood_log
             WHERE deleted_at IS NULL AND logged_at > now() - make_interval(days => %s)
            UNION ALL
            SELECT 'meal', id, place || ' (' || city || ') ' || rating || '/5',
                   concat_ws('; ', mood, note), logged_at FROM meal_log
             WHERE deleted_at IS NULL AND logged_at > now() - make_interval(days => %s)
            UNION ALL
            SELECT 'recommendation', id, place || ' (' || city || ') ' || status,
                   concat_ws('; ', 'rated ' || rating || '/5', comment), created_at FROM recommendations
             WHERE deleted_at IS NULL AND created_at > now() - make_interval(days => %s)
            ORDER BY 5
            """,
            (days, days, days),
        )
        rows = cur.fetchall()
    if not rows:
        return f"Nothing logged in the last {days} days."
    lines = []
    for kind, eid, what, detail, ts in rows:
        extra = f" — {detail}" if detail else ""
        lines.append(f"{ts.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC  {kind} #{eid}: {what}{extra}")
    return "\n".join(lines)


@mcp.tool()
def delete_entry(kind: str, entry_id: int) -> str:
    """Hide a mistaken entry (kind is "mood", "meal", "place", or
    "recommendation"). Soft delete: the entry is hidden but kept, and
    restore_entry undoes this. Ask the user before deleting."""
    table = TABLES.get(kind.strip().lower())
    if not table:
        return f"kind must be {KINDS}."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET deleted_at = now() WHERE id = %s AND deleted_at IS NULL",
            (entry_id,),
        )
        found = cur.rowcount
        conn.commit()
    if not found:
        return f"No visible {kind} #{entry_id} to delete."
    return f"Deleted {kind} #{entry_id}. (Recoverable with restore_entry.)"


@mcp.tool()
def restore_entry(kind: str, entry_id: int) -> str:
    """Bring back an entry hidden by delete_entry (kind is "mood", "meal",
    "place", or "recommendation")."""
    table = TABLES.get(kind.strip().lower())
    if not table:
        return f"kind must be {KINDS}."
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL",
            (entry_id,),
        )
        found = cur.rowcount
        conn.commit()
    if not found:
        return f"No deleted {kind} #{entry_id} to restore."
    return f"Restored {kind} #{entry_id}."


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
