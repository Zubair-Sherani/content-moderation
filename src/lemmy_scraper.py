"""
Lemmy moderation log collector.

Fetches public moderation logs from multiple Lemmy instances via the
REST API (GET /api/v3/modlog) and stores results in data/moderation.db.

Target instances: lemmy.ml, lemmy.world, beehaw.org
API docs: https://join-lemmy.org/docs/contributors/04-api.html
"""

import sqlite3
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Configuration ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH      = str(PROJECT_ROOT / "data" / "moderation.db")
REQUEST_DELAY = 1.0
PAGE_LIMIT    = 50
MAX_PAGES     = 20

INSTANCES = [
    "https://lemmy.ml",
    "https://lemmy.world",
    "https://beehaw.org",
]

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dsci511-moderation-research/1.0",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lemmy")

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    """Create Lemmy tables in the shared database."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lemmy_posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id         TEXT NOT NULL,
            instance        TEXT NOT NULL,
            community_name  TEXT,
            title           TEXT,
            body            TEXT,
            author_name     TEXT,
            url             TEXT,
            post_created_at TEXT,
            fetched_at      TEXT,
            UNIQUE(post_id, instance)
        );

        CREATE TABLE IF NOT EXISTS lemmy_modlog (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id     TEXT,
            instance    TEXT NOT NULL,
            mod_action  TEXT NOT NULL,
            reason      TEXT,
            removed     INTEGER DEFAULT 0,
            mod_name    TEXT,
            actioned_at TEXT,
            fetched_at  TEXT,
            UNIQUE(post_id, instance, mod_action, actioned_at)
        );

        CREATE INDEX IF NOT EXISTS idx_lemmy_modlog_post ON lemmy_modlog(post_id, instance);
        CREATE INDEX IF NOT EXISTS idx_lemmy_posts_inst  ON lemmy_posts(instance);
    """)
    conn.commit()
    conn.close()


# ── API helpers ────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def api_get(instance, endpoint, params=None):
    url = f"{instance}{endpoint}"
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            log.warning("Rate limited by %s — waiting 30s", instance)
            time.sleep(30)
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()
    except requests.HTTPError:
        log.warning("HTTP %s — %s%s", resp.status_code, instance, endpoint)
        return None
    except requests.RequestException as exc:
        log.error("Request failed — %s%s: %s", instance, endpoint, exc)
        return None


# ── Collection logic ───────────────────────────────────────────────────────────

def store_modlog_entry(cur, entry, instance):
    """
    Parse one modlog entry. Lemmy modlog returns a dict with one populated key
    depending on action type: mod_remove_post, mod_remove_comment, mod_ban, etc.

    Each entry looks like:
        {
          "mod_remove_post": {"reason": "hate speech", "removed": true, "when_": "..."},
          "post": {"id": 123, "name": "Title...", "body": "...", "ap_id": "..."},
          "moderator": {"name": "mod_username"},
          "community": {"name": "community_name"}
        }
    """
    # Determine action type (first key that isn't post/comment/moderator/community)
    action_keys = [k for k in entry if k.startswith("mod_")]
    if not action_keys:
        return 0, 0

    action_type = action_keys[0]
    action_data = entry[action_type]

    post_data      = entry.get("post", {})
    moderator_data = entry.get("moderator", {})

    post_id     = str(post_data.get("id", ""))
    title       = post_data.get("name", "")
    body        = post_data.get("body", "")
    author_name = entry.get("post_creator", {}).get("name", "")
    url         = post_data.get("url", "")
    created_at  = post_data.get("published", "")

    community_name = entry.get("community", {}).get("name", "")
    mod_name       = moderator_data.get("name", "")
    reason         = action_data.get("reason", "")
    removed        = 1 if action_data.get("removed", False) else 0
    actioned_at    = action_data.get("when_", "")

    # Store the post if we have one
    post_new = 0
    if post_id:
        cur.execute(
            """INSERT OR IGNORE INTO lemmy_posts
                   (post_id, instance, community_name, title, body,
                    author_name, url, post_created_at, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (post_id, instance, community_name, title, body,
             author_name, url, created_at, now_iso()),
        )
        post_new = cur.rowcount

    cur.execute(
        """INSERT OR IGNORE INTO lemmy_modlog
               (post_id, instance, mod_action, reason, removed,
                mod_name, actioned_at, fetched_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (post_id, instance, action_type, reason, removed,
         mod_name, actioned_at, now_iso()),
    )
    log_new = cur.rowcount
    return post_new, log_new


def collect_instance(instance):
    """Paginate through an instance's full modlog."""
    page = total_posts = total_logs = 0

    while page < MAX_PAGES:
        page += 1
        data = api_get(instance, "/api/v3/modlog", params={
            "limit": PAGE_LIMIT,
            "page":  page,
            "type_": "ModRemovePost",  # only post removals; change to "All" for everything
        })

        if not data:
            break

        # Lemmy 0.19+ returns {"removed_posts": [...]}; older returns {"data": [...]}
        entries = (data.get("removed_posts")
                   or data.get("data", {}).get("removed_posts", [])
                   or [])

        if not entries:
            break

        conn = get_conn()
        cur  = conn.cursor()
        for entry in entries:
            p, l = store_modlog_entry(cur, entry, instance)
            total_posts += p
            total_logs  += l
        conn.commit()
        conn.close()

    log.info("%s → %d posts, %d modlog entries", instance, total_posts, total_logs)
    return total_posts, total_logs


def collect_all_instances():
    setup_db()
    grand_posts = grand_logs = 0
    for instance in INSTANCES:
        p, l = collect_instance(instance)
        grand_posts += p
        grand_logs  += l
    log.info("Done — %d posts, %d modlog entries total", grand_posts, grand_logs)
    return grand_posts, grand_logs


if __name__ == "__main__":
    collect_all_instances()
