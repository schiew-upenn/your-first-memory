"""your-first-memory — a habit tracker and mood log for a model that has none.

Last week's instrument gave your model a sense of time. But ask it
"how many days in a row have I run?" or "was I happier on days I
meditated?" and it can only guess: nothing survives the end of a
conversation. This server keeps two small logs — habits done, moods
felt — so the model can answer from a *record* instead. See docs/adr/
for every choice made here — each one records a real decision with the
road not taken. ADR-0005 covers what changed from the quotes template.
"""
import os
from datetime import timezone
from mcp.server.fastmcp import FastMCP

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL")

mcp = FastMCP(
    "your-first-memory",
    instructions=(
        "A habit tracker and mood log. Only call log_habit for something the "
        "user says they actually did (not something they plan or are thinking "
        "about), and only call log_mood for a mood they actually report. Tell "
        "them what you logged, with its entry id, so a mistake can be undone "
        "with delete_entry. Streaks and patterns (e.g. 'am I happier on days I "
        "exercise?') are answered by reading show_history, not guessed."
    ),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
)

# Soft delete (ADR-0005): deleted_at hides a row from history; it is never
# removed, so restore_entry can bring it back.
SCHEMA = """
CREATE TABLE IF NOT EXISTS habit_log (
    id         SERIAL PRIMARY KEY,
    habit      TEXT NOT NULL,
    note       TEXT,                           -- optional, like `who` was (ADR-0004)
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS mood_log (
    id         SERIAL PRIMARY KEY,
    mood       TEXT NOT NULL,
    reason     TEXT,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
"""

# kind -> table. Table names can't be SQL parameters, so only these two
# fixed strings ever reach the query text.
TABLES = {"habit": "habit_log", "mood": "mood_log"}


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


@mcp.tool()
def log_habit(habit: str, note: str = "") -> str:
    """Record that the user did a habit just now (e.g. "run", "meditate",
    "read 20 pages"). Use the same short name each time so streaks line up.
    `note` is optional detail ("5k, felt easy")."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO habit_log (habit, note) VALUES (%s, %s) RETURNING id, logged_at",
            (habit.strip().lower(), note or None),
        )
        hid, ts = cur.fetchone()
        conn.commit()
    return f"Logged habit #{hid} ({habit}) at {ts.isoformat()}."


@mcp.tool()
def log_mood(mood: str, reason: str = "") -> str:
    """Record how the user feels right now (e.g. "stressed", "happy",
    "tired"). `reason` is optional — a mood you can't explain still counts."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mood_log (mood, reason) VALUES (%s, %s) RETURNING id, logged_at",
            (mood.strip().lower(), reason or None),
        )
        mid, ts = cur.fetchone()
        conn.commit()
    return f"Logged mood #{mid} ({mood}) at {ts.isoformat()}."


@mcp.tool()
def show_history(days: int = 7) -> str:
    """Habits and moods from the last `days` days, oldest first, both logs
    interleaved on one timeline. Deleted entries are left out. Times are UTC."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 'habit', id, habit, note, logged_at FROM habit_log
             WHERE deleted_at IS NULL AND logged_at > now() - make_interval(days => %s)
            UNION ALL
            SELECT 'mood', id, mood, reason, logged_at FROM mood_log
             WHERE deleted_at IS NULL AND logged_at > now() - make_interval(days => %s)
            ORDER BY logged_at
            """,
            (days, days),
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
    """Hide a mistaken entry (kind is "habit" or "mood"). Soft delete: the
    entry leaves show_history but is kept, and restore_entry undoes this."""
    table = TABLES.get(kind.strip().lower())
    if not table:
        return 'kind must be "habit" or "mood".'
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
    """Bring back an entry hidden by delete_entry (kind is "habit" or "mood")."""
    table = TABLES.get(kind.strip().lower())
    if not table:
        return 'kind must be "habit" or "mood".'
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
