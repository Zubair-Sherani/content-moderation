# Cross-Platform Content Moderation Standards Dataset

**DSCI 511 — Data Acquisition & Pre-Processing**  
Zubair Khan · Albina | Drexel University

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Research Question](#research-question)
3. [Repository Structure](#repository-structure)
4. [Data Sources](#data-sources)
5. [Quickstart](#quickstart)
6. [Running the Notebooks](#running-the-notebooks)
7. [Database Schema](#database-schema)
8. [Data Cleaning Pipeline](#data-cleaning-pipeline)
9. [Perspective API Enrichment](#perspective-api-enrichment)
10. [Challenges & Limitations](#challenges--limitations)
11. [Upcoming Work](#upcoming-work)
12. [References](#references)

---

## Project Overview

This project builds a reproducible, cross-platform content moderation dataset by collecting moderation decisions and flagged content from two open platforms — **BlueSky** (via the AT Protocol) and **Lemmy** (a federated, open-source Reddit alternative) — and enriching every post with automated toxicity scores from **Google's Perspective API**.

The dataset enables researchers to ask: when different platforms invoke the same moderation category (hate speech, harassment, incivility), are they actually filtering the same kind of content? And where do human moderation decisions and automated toxicity classifiers agree or diverge?

---

## Research Question

> When platforms like BlueSky and Lemmy claim to moderate for "hate speech" or "harassment" — are they actually flagging the same kind of content?

Platforms use the same category names but enforce them in community-specific, often inconsistent ways. This dataset pairs human moderation labels with automated Perspective API scores on the same text, making that divergence measurable.

---

## Repository Structure

```
.
├── notebooks/
│   ├── 01_bluesky_collection.ipynb       # BlueSky post + label collection
│   ├── 02_lemmy_collection.ipynb         # Lemmy modlog collection (3 instances)
│   ├── 03_reddit_collection.ipynb        # Reddit collection via PRAW (pending API)
│   ├── 03_reddit_collection_normvio.ipynb# Reddit NormVio dataset loader
│   ├── 04_perspective_enrichment.ipynb   # Perspective API scoring
│   └── 05_data_cleaning.ipynb            # Preprocessing & cleaning pipeline
│
├── src/
│   ├── bluesky_scraper.py                # AT Protocol collection logic
│   ├── lemmy_scraper.py                  # Lemmy modlog collection logic
│   ├── reddit_scraper.py                 # PRAW-based Reddit collection
│   └── perspective_enrichment.py         # Perspective API scoring pipeline
│
├── data/
│   ├── moderation.db                     # SQLite database (git-ignored)
│   └── raw/
│       └── normvio/                      # Reddit NormVio JSONL files
│           ├── train.jsonl
│           ├── dev.jsonl
│           └── test.jsonl
│
├── .env.example                          # API key template
├── .gitignore
├── requirements.txt
├── generate_slides.py                    # Generates DSCI511_Presentation.pptx
└── README.md
```

---

## Data Sources

### 1. BlueSky / AT Protocol
BlueSky is a decentralized social network built on the AT Protocol. Its moderation system is open — labeling events are embedded directly in post responses when the correct request header is set.

- **Endpoint:** `https://api.bsky.app/xrpc/app.bsky.feed.searchPosts`
- **Authentication:** None required
- **What we collect:** Post text, author, timestamps, engagement counts, embedded moderation labels
- **Labelers queried:** Bluesky Moderation Service (`did:plc:ar7c4by46qjdydhdevvrndac`)
- **Queries used:**
  - Discussion queries: `hate speech`, `harassment`, `misinformation`, `spam`, `threatening`
  - Content queries: `porn`, `nudity`, `graphic-media`
- **Current volume:** 7,792 posts · 1,491 labels · 58 label definitions

### 2. Lemmy
Lemmy is a federated, open-source Reddit alternative. Every instance publishes a fully public moderation log accessible via REST API.

- **Endpoint:** `GET /api/v3/modlog`
- **Authentication:** None required
- **Instances collected:**
  | Instance | Focus | Reason rate |
  |----------|-------|-------------|
  | lemmy.ml | Tech / strict | 95.9% |
  | lemmy.world | General / largest | 97.3% |
  | beehaw.org | Community-first | 93.6% |
- **What we collect:** Post title, body, moderator reason, removal status, mod username, timestamps
- **Current volume:** 2,865 posts · 3,000 modlog entries

### 3. Reddit *(pending)*
Reddit collection is implemented via PRAW but awaiting API access approval from Reddit. The scraper is fully built at `src/reddit_scraper.py`.

- **Library:** PRAW (Python Reddit API Wrapper)
- **Planned subreddits:** politics, worldnews, news, science, AskReddit, todayilearned
- **Status:** Requires `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env`

### 4. Reddit NormVio Dataset *(supplementary)*
A pre-labeled academic dataset of Reddit norm violations included as supplementary reference data. Note: post text is **redacted** in this dataset — only IDs are present, so Perspective API cannot be run on it.

- **Volume:** 52,012 labeled comments across 2,080 subreddits
- **Table:** `reddit_normvio_clean`

### 5. Google Perspective API *(enrichment)*
Applied to all collected BlueSky and Lemmy posts. Returns probability scores (0–1) across six toxicity dimensions.

| Attribute | What it measures |
|-----------|-----------------|
| `toxicity` | General rude or disrespectful tone |
| `severe_toxicity` | Hateful or threatening content |
| `identity_attack` | Negative stereotyping of identity groups |
| `insult` | Insulting or demeaning language |
| `profanity` | Swearing or obscene language |
| `threat` | Expressed intent to harm |

---

## Quickstart

### 1. Clone the repository
```bash
git clone https://github.com/Zubair-Sherani/content-moderation.git
cd content-moderation
```

### 2. Create a virtual environment and install dependencies
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API keys
```bash
cp .env.example .env
```
Open `.env` and fill in your credentials:
```
PERSPECTIVE_API_KEY=your_key_here
REDDIT_CLIENT_ID=your_client_id         # optional — only needed for Reddit
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USER_AGENT=dsci511-moderation-research/1.0
```

- **Perspective API key:** Apply at https://developers.perspectiveapi.com/s/docs-get-started
- **Reddit credentials:** Create a script app at https://www.reddit.com/prefs/apps

> BlueSky (notebook 01) and Lemmy (notebook 02) require **no credentials**.

### 4. Launch Jupyter and run notebooks in order
```bash
jupyter lab
```

---

## Running the Notebooks

Run notebooks **in this order**. Each one builds on the previous.

| # | Notebook | What it does | Credentials needed |
|---|----------|-------------|-------------------|
| 01 | `01_bluesky_collection.ipynb` | Fetches posts + labels from BlueSky API | None |
| 02 | `02_lemmy_collection.ipynb` | Fetches modlogs from 3 Lemmy instances | None |
| 03 | `03_reddit_collection.ipynb` | Collects Reddit posts via PRAW | Reddit API keys |
| 05 | `05_data_cleaning.ipynb` | Cleans all collected data, builds `posts_for_scoring` | None |
| 04 | `04_perspective_enrichment.ipynb` | Scores posts with Perspective API | Perspective API key |

> Note: Run notebook 05 (cleaning) **before** notebook 04 (Perspective). The enrichment reads from the `posts_for_scoring` table that cleaning produces.

### Running scrapers directly (no Jupyter)
Each `src/` module can also be run as a standalone script from the project root:
```bash
python src/bluesky_scraper.py
python src/lemmy_scraper.py
python src/reddit_scraper.py        # requires Reddit credentials in .env
python src/perspective_enrichment.py # requires Perspective key in .env
```

### Checking database state at any time
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/moderation.db')
for t in ['bsky_posts','bsky_labels','lemmy_posts','lemmy_modlog',
          'bsky_posts_clean','lemmy_posts_clean','posts_for_scoring','perspective_scores']:
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t:<25}: {n:,} rows')
    except:
        print(f'  {t:<25}: not yet created')
"
```

---

## Database Schema

All data is stored in a single SQLite database at `data/moderation.db`. The file is git-ignored (generated data, not source code).

### BlueSky tables

**`bsky_posts`** — Raw collected posts
| Column | Type | Description |
|--------|------|-------------|
| `uri` | TEXT PK | AT Protocol URI — unique post identifier |
| `cid` | TEXT | Content identifier (hash) |
| `author_did` | TEXT | Author's decentralized identifier |
| `author_handle` | TEXT | Author's BlueSky handle |
| `text` | TEXT | Full post text |
| `lang` | TEXT | Language tag declared by author (e.g. `en`) |
| `post_created_at` | TEXT | ISO timestamp when post was created |
| `like_count` | INTEGER | Likes at time of collection |
| `reply_count` | INTEGER | Replies at time of collection |
| `repost_count` | INTEGER | Reposts at time of collection |
| `search_query` | TEXT | Query used to find this post |
| `fetched_at` | TEXT | ISO timestamp when we collected it |

**`bsky_labels`** — Moderation labels attached to posts
| Column | Type | Description |
|--------|------|-------------|
| `uri` | TEXT | Post URI (links to `bsky_posts`) |
| `label_val` | TEXT | Label value (e.g. `porn`, `self-harm`, `graphic-media`) |
| `label_src` | TEXT | DID of the labeler that applied it |
| `is_negation` | INTEGER | 1 if this label negates a prior label |
| `labeled_at` | TEXT | ISO timestamp when label was applied |

**`labelers`** — Known labeling services
| Column | Type | Description |
|--------|------|-------------|
| `did` | TEXT PK | Labeler's decentralized identifier |
| `name` | TEXT | Display name |
| `created_at` | TEXT | When the labeler was registered |

**`label_definitions`** — What each label value means
| Column | Type | Description |
|--------|------|-------------|
| `labeler_did` | TEXT | Which labeler defines this label |
| `identifier` | TEXT | Label value (e.g. `self-harm`) |
| `severity` | TEXT | `alert`, `inform`, or `none` |
| `blurs` | TEXT | `content`, `media`, or `none` |
| `description` | TEXT | Human-readable description |

> Note: Built-in AT Protocol labels (`porn`, `nudity`, `sexual`, `graphic-media`) do **not** have entries in `label_definitions` — their behaviour is baked into AT Protocol clients.

---

### Lemmy tables

**`lemmy_posts`** — Post content from moderated threads
| Column | Type | Description |
|--------|------|-------------|
| `post_id` | TEXT | Lemmy post ID (numeric string) |
| `instance` | TEXT | Full instance URL (e.g. `https://lemmy.ml`) |
| `community_name` | TEXT | Community the post was in |
| `title` | TEXT | Post title |
| `body` | TEXT | Post body (null for link posts) |
| `author_name` | TEXT | Poster's username |
| `post_created_at` | TEXT | When the post was created |

**`lemmy_modlog`** — Moderation actions taken on posts
| Column | Type | Description |
|--------|------|-------------|
| `post_id` | TEXT | Links to `lemmy_posts` |
| `instance` | TEXT | Which instance this action came from |
| `mod_action` | TEXT | Action type (e.g. `mod_remove_post`) |
| `reason` | TEXT | Moderator's stated reason (nullable — ~4% are blank) |
| `removed` | INTEGER | 1 if post was removed |
| `mod_name` | TEXT | Moderator's username |
| `actioned_at` | TEXT | When the action was taken |

---

### Cleaned tables

**`bsky_posts_clean`** — BlueSky posts after cleaning
Adds: `text_clean` (normalized text), `is_english` (0/1), `text_length`

**`lemmy_posts_clean`** — Lemmy posts joined with modlog, after cleaning
Adds: `text_combined` (title + body), `text_clean`, `text_length`, `reason_missing` (0/1)

**`posts_for_scoring`** — Unified input table for Perspective API
| Column | Description |
|--------|-------------|
| `platform` | `bluesky` or `lemmy` |
| `post_id` | Platform-specific unique ID |
| `text_clean` | Normalized post text |
| `label_context` | Human label or moderation reason |
| `scored` | 0 = not yet scored, 1 = done |

**`perspective_scores`** — Perspective API results
| Column | Description |
|--------|-------------|
| `platform` | Source platform |
| `post_id` | Links back to `posts_for_scoring` |
| `toxicity` | Score 0–1 |
| `severe_toxicity` | Score 0–1 |
| `identity_attack` | Score 0–1 |
| `insult` | Score 0–1 |
| `profanity` | Score 0–1 |
| `threat` | Score 0–1 |
| `scored_at` | ISO timestamp |

---

## Data Cleaning Pipeline

Notebook `05_data_cleaning.ipynb` applies the following steps in sequence:

| Step | Applied to | What it does |
|------|-----------|--------------|
| Null removal | BlueSky | Drops 40 posts with no text |
| Short text filter | Both | Drops texts under 10 characters after normalization |
| Deduplication | Both | Keeps oldest copy of duplicate texts; removes 500+ spam duplicates |
| Text normalization | Both | Strips URLs, @mentions, collapses whitespace |
| Language detection | BlueSky | Uses `lang` field; falls back to `langdetect` for null entries |
| English filter | BlueSky | Flags non-English posts; excludes from Perspective scoring |
| Title + body merge | Lemmy | Combines title and body into `text_clean` for link posts |
| Reason flagging | Lemmy | Sets `reason_missing=1` for 132 modlog entries with no stated reason |
| Invalid label filter | BlueSky | Regex validator at insert time rejects non-AT-Protocol label values |

**Results:** 7,792 raw BlueSky posts → 7,198 clean (6,161 English) | 2,865 Lemmy posts → 1,570 clean

---

## Perspective API Enrichment

Notebook `04_perspective_enrichment.ipynb` scores all posts in `posts_for_scoring` that have not yet been scored.

**Rate limit:** Free tier is 1 QPS (60 requests/minute). Scoring all 7,731 posts takes approximately 2 hours.

The pipeline is **resumable** — it checks which posts are already in `perspective_scores` and skips them. You can stop and restart at any time without losing progress.

To score in batches, set `BATCH_SIZE` in Cell 1 of the notebook:
```python
BATCH_SIZE = 100    # score 100 posts (~2 min)
BATCH_SIZE = None   # score everything remaining (~2 hrs)
```

**Preliminary results (BlueSky):**

| Attribute | Average score |
|-----------|--------------|
| Toxicity | 0.130 |
| Severe toxicity | 0.015 |
| Identity attack | 0.032 |
| Insult | 0.062 |
| Profanity | 0.085 |
| Threat | 0.021 |

Key finding: posts labeled by BlueSky for adult content (`porn`, `nudity`) do not score high on toxicity — the human label captures content type while Perspective measures hostility and aggression. These are measuring different dimensions of harm.

---

## Challenges & Limitations

### Encountered & resolved

**BlueSky cursor pagination blocked (HTTP 403)**  
Cursor-based pagination returns 403 after page 1 for unauthenticated requests. Fixed by switching to date-windowed pagination: each page, the oldest post's timestamp minus 1 second becomes the `until` parameter for the next request.

**Zero labels from discussion queries**  
Queries like `"hate speech"` returned zero labeled posts. BlueSky labels actual content (explicit media, self-harm) not discussions about moderation. Fixed by adding content-targeted queries (`porn`, `nudity`, `graphic-media`).

**Invalid label values from third-party labelers**  
Some labelers embed engagement metadata as label values (e.g. `comment_count:23`, `reaction_count:142`). These are not moderation labels. Fixed with a regex validator at insert time: only values matching `^!?[a-z][a-z0-9-]*$` are accepted.

**Foreign key constraint blocking community labeler inserts**  
An early schema version had a `FOREIGN KEY` on `bsky_labels.label_src` requiring every labeler to be pre-registered. Community labeler DIDs from post responses are not fetched ahead of time, so every community-labeled insert failed. Fixed via a runtime `PRAGMA foreign_key_list()` migration that detects and drops the constraint.

**Missing `search_query` column on existing databases**  
Adding a new column to an existing table with `CREATE TABLE IF NOT EXISTS` silently skips the addition. Fixed with a `PRAGMA table_info()` check followed by `ALTER TABLE ... ADD COLUMN` if missing.

### Current limitations

**Reddit API approval pending**  
Reddit introduced a Responsible Builder Policy gate mid-project. The PRAW scraper (`src/reddit_scraper.py`) is fully implemented and ready to run, but requires API credentials that are awaiting approval.

**NormVio dataset — no post text**  
The Reddit NormVio academic dataset (used as supplementary reference) has all post text redacted — only comment IDs are present. Perspective API cannot be run on this data, and cross-platform text comparison with Reddit is not possible from this source alone.

**Lemmy blank reason fields**  
Approximately 4.4% of modlog entries across all three instances have no stated removal reason. Moderators are not required to provide reasons on Lemmy. These records are retained and flagged (`reason_missing=1`) but excluded from reason-based analysis.

**Perspective API rate limit**  
The free tier allows 1 request per second. Scoring the full dataset (~7,700 posts) takes approximately 2 hours. A quota increase request to Google can raise this limit for bulk runs.

**Language coverage**  
Perspective API is optimized for English. Approximately 9% of BlueSky posts have a non-English or unknown language tag. These are detected using the `langdetect` library and excluded from scoring, reducing the scoreable BlueSky dataset from 7,198 to 6,161 posts.

**BlueSky label skew toward adult content**  
73% of all BlueSky labels are `porn`. This reflects the focus of the official labeling service rather than the full spectrum of moderation. Hate speech and harassment labeling on BlueSky is sparse and inconsistent.

---

## Upcoming Work

- Complete Perspective API scoring across all 7,731 posts
- Reddit data collection once API approval is granted
- Cross-platform toxicity comparison: BlueSky vs Lemmy score distributions
- Human label vs Perspective score alignment analysis — where do they disagree?
- Instance-level comparison across three Lemmy instances
- Unified cleaned export table joining all platforms and all signals
- Full data dictionary for every field
- Phase 2 report: findings, methodology, obstacles

---

## References

1. BlueSky / AT Protocol Documentation — https://docs.bsky.app/docs/advanced-guides/atproto
2. Lemmy REST API Reference — https://join-lemmy.org/docs/contributors/04-api.html
3. Google Perspective API — https://perspectiveapi.com/
4. PRAW — Python Reddit API Wrapper — https://praw.readthedocs.io/
5. Gebru et al. (2018). *Datasheets for Datasets* — https://dl.acm.org/doi/pdf/10.1145/3458723
6. NormVio Dataset — Reddit Norm Violation research dataset
