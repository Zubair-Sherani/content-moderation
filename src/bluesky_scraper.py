"""
BlueSky / AT Protocol moderation data collector.

Collects posts + embedded labels from the BlueSky public API and stores them
in the shared SQLite database (data/moderation.db).

Usage:
    python src/bluesky_scraper.py
or import and call collect_all_posts() from a notebook.
"""

import re
import sqlite3
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ── Configuration ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH      = str(PROJECT_ROOT / "data" / "moderation.db")
API_BASE     = "https://api.bsky.app/xrpc"
REQUEST_DELAY = 1.0
LIMIT         = 100
MAX_PAGES     = 10

SEARCH_QUERIES = ["hate speech", "harassment", "misinformation", "spam", "threatening"]
LABEL_QUERIES  = ["porn", "nudity", "graphic-media"]
ALL_QUERIES    = SEARCH_QUERIES + LABEL_QUERIES

LABELER_DIDS = [
    "did:plc:ar7c4by46qjdydhdevvrndac",  # Bluesky Moderation Service (official)
]
LABELERS_HEADER = ",".join(LABELER_DIDS)

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dsci511-moderation-research/1.0",
    "atproto-accept-labelers": LABELERS_HEADER,
}

_VALID_LABEL = re.compile(r"^!?[a-z][a-z0-9-]*$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bluesky")

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    """Create BlueSky tables if they don't exist; run any needed migrations."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    cur  = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS labelers (
            did          TEXT PRIMARY KEY,
            name         TEXT,
            created_at   TEXT,
            fetched_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS label_definitions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            labeler_did     TEXT NOT NULL REFERENCES labelers(did),
            identifier      TEXT NOT NULL,
            severity        TEXT,
            blurs           TEXT,
            default_setting TEXT,
            description     TEXT,
            UNIQUE(labeler_did, identifier)
        );

        CREATE TABLE IF NOT EXISTS bsky_posts (
            uri             TEXT PRIMARY KEY,
            cid             TEXT,
            author_did      TEXT,
            author_handle   TEXT,
            text            TEXT,
            lang            TEXT,
            post_created_at TEXT,
            like_count      INTEGER DEFAULT 0,
            reply_count     INTEGER DEFAULT 0,
            repost_count    INTEGER DEFAULT 0,
            search_query    TEXT,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS bsky_labels (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uri         TEXT NOT NULL,
            cid         TEXT,
            label_val   TEXT NOT NULL,
            label_src   TEXT NOT NULL,
            is_negation INTEGER DEFAULT 0,
            labeled_at  TEXT,
            platform    TEXT DEFAULT 'bluesky',
            UNIQUE(uri, label_val, label_src)
        );

        CREATE INDEX IF NOT EXISTS idx_bsky_labels_uri ON bsky_labels(uri);
        CREATE INDEX IF NOT EXISTS idx_bsky_labels_val ON bsky_labels(label_val);
        CREATE INDEX IF NOT EXISTS idx_bsky_posts_uri  ON bsky_posts(uri);
    """)

    # Migration: add search_query if missing (old schema)
    existing = {row[1] for row in cur.execute("PRAGMA table_info(bsky_posts)")}
    if "search_query" not in existing:
        cur.execute("ALTER TABLE bsky_posts ADD COLUMN search_query TEXT")

    # Migration: drop FK on bsky_labels.label_src if present (blocks community labelers)
    fk_list = cur.execute("PRAGMA foreign_key_list(bsky_labels)").fetchall()
    if any(row[2] == "labelers" for row in fk_list):
        cur.executescript("""
            DROP TABLE IF EXISTS bsky_labels;
            CREATE TABLE bsky_labels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                uri         TEXT NOT NULL,
                cid         TEXT,
                label_val   TEXT NOT NULL,
                label_src   TEXT NOT NULL,
                is_negation INTEGER DEFAULT 0,
                labeled_at  TEXT,
                platform    TEXT DEFAULT 'bluesky',
                UNIQUE(uri, label_val, label_src)
            );
            CREATE INDEX IF NOT EXISTS idx_bsky_labels_uri ON bsky_labels(uri);
            CREATE INDEX IF NOT EXISTS idx_bsky_labels_val ON bsky_labels(label_val);
        """)

    conn.commit()
    conn.close()


# ── API helpers ────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def api_get(endpoint, params=None):
    url = f"{API_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            log.warning("Rate limited — waiting 30s")
            time.sleep(30)
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()
    except requests.HTTPError:
        log.warning("HTTP %s — %s: %s", resp.status_code, endpoint, resp.text[:200])
        return None
    except requests.RequestException as exc:
        log.error("Request failed — %s: %s", endpoint, exc)
        return None


# ── Collection logic ───────────────────────────────────────────────────────────

def fetch_labeler_metadata():
    data = api_get("app.bsky.labeler.getServices", params={
        "dids": LABELER_DIDS,
        "detailed": "true",
    })
    if not data or "views" not in data:
        log.error("No labeler data returned: %s", data)
        return

    conn = get_conn()
    cur  = conn.cursor()

    for view in data["views"]:
        creator  = view.get("creator", {})
        did      = creator.get("did", "")
        name     = creator.get("displayName") or creator.get("handle", "unknown")
        policies = view.get("policies", {})

        cur.execute(
            "INSERT OR IGNORE INTO labelers (did, name, created_at, fetched_at) VALUES (?,?,?,?)",
            (did, name, view.get("indexedAt", ""), now_iso()),
        )

        for defn in policies.get("labelValueDefinitions", []):
            description = ""
            for locale in defn.get("locales", []):
                if locale.get("lang") == "en":
                    description = locale.get("description", "")
                    break
            if not description and defn.get("locales"):
                description = defn["locales"][0].get("description", "")

            cur.execute(
                """INSERT OR IGNORE INTO label_definitions
                       (labeler_did, identifier, severity, blurs, default_setting, description)
                   VALUES (?,?,?,?,?,?)""",
                (did, defn.get("identifier", ""), defn.get("severity", ""),
                 defn.get("blurs", ""), defn.get("defaultSetting", ""), description),
            )

    conn.commit()
    conn.close()
    log.info("Labeler metadata stored")


def store_post_and_labels(cur, post, query):
    """Insert one post and its labels. Returns (post_inserted, labels_inserted)."""
    uri    = post.get("uri", "")
    cid    = post.get("cid", "")
    author = post.get("author", {})
    record = post.get("record", {})
    langs  = record.get("langs", [])

    cur.execute(
        """INSERT OR IGNORE INTO bsky_posts
               (uri, cid, author_did, author_handle, text, lang,
                post_created_at, like_count, reply_count, repost_count,
                search_query, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uri, cid,
         author.get("did", ""), author.get("handle", ""),
         record.get("text", ""), langs[0] if langs else None,
         record.get("createdAt", ""),
         post.get("likeCount", 0), post.get("replyCount", 0), post.get("repostCount", 0),
         query, now_iso()),
    )
    post_new = cur.rowcount

    labels_new = 0
    for label in post.get("labels", []):
        val = label.get("val", "")
        src = label.get("src", "")
        if not val or not src or not _VALID_LABEL.match(val):
            continue
        cur.execute(
            """INSERT OR IGNORE INTO bsky_labels
                   (uri, cid, label_val, label_src, is_negation, labeled_at)
               VALUES (?,?,?,?,?,?)""",
            (uri, cid, val, src, 1 if label.get("neg") else 0, label.get("cts", "")),
        )
        labels_new += cur.rowcount

    return post_new, labels_new


def collect_posts_for_query(query):
    """Date-windowed pagination (cursor pagination blocked after page 1 without auth)."""
    until_ts = None
    page = total_posts = total_labels = 0

    while page < MAX_PAGES:
        params = {"q": query, "limit": LIMIT}
        if until_ts:
            params["until"] = until_ts

        data = api_get("app.bsky.feed.searchPosts", params=params)
        if not data or not data.get("posts"):
            break

        posts  = data["posts"]
        conn   = get_conn()
        cur    = conn.cursor()
        for post in posts:
            p, l = store_post_and_labels(cur, post, query)
            total_posts  += p
            total_labels += l
        conn.commit()
        conn.close()

        page += 1
        oldest = min((p.get("indexedAt", "") for p in posts if p.get("indexedAt")), default="")
        if not oldest:
            break
        try:
            dt = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            until_ts = (dt - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            break

    log.info("'%s' → %d posts, %d labels", query, total_posts, total_labels)
    return total_posts, total_labels


def collect_all_posts():
    setup_db()
    fetch_labeler_metadata()
    grand_posts = grand_labels = 0
    for query in ALL_QUERIES:
        p, l = collect_posts_for_query(query)
        grand_posts  += p
        grand_labels += l
    log.info("Done — %d posts, %d labels total", grand_posts, grand_labels)
    return grand_posts, grand_labels


if __name__ == "__main__":
    collect_all_posts()
