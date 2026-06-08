"""
Reddit post collector using PRAW.

Collects posts from moderation-heavy subreddits and stores them in
data/moderation.db. Removal status is inferred from post body = "[removed]".

Requires credentials in .env:
    REDDIT_CLIENT_ID=...
    REDDIT_CLIENT_SECRET=...
    REDDIT_USER_AGENT=dsci511-moderation-research/1.0

Get credentials at: https://www.reddit.com/prefs/apps  (script app type)
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Configuration ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH      = str(PROJECT_ROOT / "data" / "moderation.db")
POST_LIMIT   = 500  # posts to fetch per subreddit (max 1000 with PRAW)

# Subreddits with clearly published moderation rules
# Mix of high-volume and strict-moderation communities
SUBREDDITS = [
    "politics",
    "worldnews",
    "news",
    "science",
    "AskReddit",
    "todayilearned",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reddit")

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    """Create Reddit table in the shared database."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reddit_posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id         TEXT UNIQUE,
            subreddit       TEXT NOT NULL,
            title           TEXT,
            selftext        TEXT,
            author_name     TEXT,
            is_removed      INTEGER DEFAULT 0,
            removal_reason  TEXT,
            score           INTEGER DEFAULT 0,
            num_comments    INTEGER DEFAULT 0,
            url             TEXT,
            post_created_at TEXT,
            fetched_at      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_reddit_posts_sub     ON reddit_posts(subreddit);
        CREATE INDEX IF NOT EXISTS idx_reddit_posts_removed ON reddit_posts(is_removed);
    """)
    conn.commit()
    conn.close()


# ── API helpers ────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_reddit_client():
    client_id     = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent    = os.getenv("REDDIT_USER_AGENT", "dsci511-moderation-research/1.0")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in .env"
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


# ── Collection logic ───────────────────────────────────────────────────────────

def collect_subreddit(reddit, subreddit_name):
    """
    Fetch recent 'new' posts from a subreddit.
    Removed posts have selftext == '[removed]'; we record that status.
    """
    conn  = get_conn()
    cur   = conn.cursor()
    count = 0

    try:
        sub = reddit.subreddit(subreddit_name)
        for post in sub.new(limit=POST_LIMIT):
            is_removed = 1 if post.selftext == "[removed]" else 0
            created_at = datetime.fromtimestamp(
                post.created_utc, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")

            cur.execute(
                """INSERT OR IGNORE INTO reddit_posts
                       (post_id, subreddit, title, selftext, author_name,
                        is_removed, score, num_comments, url,
                        post_created_at, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post.id, subreddit_name,
                    post.title,
                    post.selftext if not is_removed else None,
                    str(post.author) if post.author else "[deleted]",
                    is_removed,
                    post.score, post.num_comments,
                    f"https://reddit.com{post.permalink}",
                    created_at, now_iso(),
                ),
            )
            count += cur.rowcount

        conn.commit()
    except Exception as exc:
        log.error("Error collecting r/%s: %s", subreddit_name, exc)
    finally:
        conn.close()

    log.info("r/%s → %d new posts", subreddit_name, count)
    return count


def collect_all_subreddits():
    setup_db()
    reddit = get_reddit_client()
    total  = 0
    for sub in SUBREDDITS:
        total += collect_subreddit(reddit, sub)
    log.info("Done — %d posts total", total)
    return total


if __name__ == "__main__":
    collect_all_subreddits()
