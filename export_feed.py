#!/usr/bin/env python3
"""Export a rolling JSON feed of pushed journal-watch papers for the iOS app.

Reads data/journal_watch.db and writes feed.json containing papers that were
pushed (status='notified') within the last N days, deduplicated by DOI,
newest first. The app reads this file via raw.githubusercontent.com once it
is committed to the repo; nothing phones home and no LLM is involved in
search (RSS + Crossref + keyword filter already happened upstream).

Two enrichment steps run here (2026-11-13, feed contract v3):

1. OpenAlex OA lookup: fills pdf_url / is_open_access per paper from
   OpenAlex (no key, no email needed). A DOI OpenAlex has no record for
   yet (typically 1-3 days after publication) stays null -- null means
   "unknown", never "closed". A lookup failure leaves all fields null.

2. New-journal catch-up: papers from journals added to journals.yaml
   within the last 7 days (added_on field) may enter the feed when
   published up to 45 days ago, provided they were discovered in the
   rolling window. This covers the one-time catch-up when a journal is
   added (e.g. Nature Reviews Clean Technology reviews published weeks
   before monitoring started). The naive rule -- admit anything
   discovered recently regardless of pub date -- would flood the feed in
   the GitHub Actions runner, whose DB resets to the repo snapshot every
   run and therefore "discovers" the same months-old Joule RSS backlog
   every day (Joule's inpress feed lists back to June; measured
   2026-11-13: 25 filter-passing items older than 45 days). The
   new-journal gate is what keeps the steady-state feed tight.

OA source is Unpaywall (per-DOI, free, email-identified), not OpenAlex:
OpenAlex's keyless tier shares one daily budget per egress IP and it is
already exhausted by the time this runs, so it 429s. Unpaywall answers
per DOI with is_oa / best_oa_location.url_for_pdf; a 404 (DOI not
indexed yet, typically 1-2 days after publication) means unknown.
The email used is the repo owner's GitHub noreply address.

Usage:
    python3 export_feed.py [--days 3] [--out feed.json] [--db data/journal_watch.db]
"""
import argparse
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OA_BATCH_SIZE = 50
NEW_JOURNAL_WINDOW_DAYS = 7
CATCHUP_PUB_CAP_DAYS = 45
# Unpaywall (free, email-identified). Uses the repo owner's GitHub noreply
# address -- valid format, already public in the repo's commit history.
UNPAYWALL_EMAIL = "59205919+dengw666@users.noreply.github.com"
UNPAYWALL_SLEEP = 0.3


def clean_title(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def parse_authors(a):
    if not a:
        return []
    try:
        v = json.loads(a)
        return v if isinstance(v, list) else [str(v)]
    except (ValueError, TypeError):
        return [a]


def load_new_journals(config_path, since_days=NEW_JOURNAL_WINDOW_DAYS):
    """Journal names added within the last `since_days` days.

    Reads added_on: YYYY-MM-DD from journals.yaml with a small line scan
    (no YAML dependency -- the exporter must run on stdlib only in the
    Actions runner). Missing/unparseable config returns an empty set and
    the feed falls back to the plain 3-day pub-date rule.
    """
    today = datetime.now(timezone.utc).date()
    try:
        text = Path(config_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"config not readable ({config_path}): {e}; no new-journal exception", file=sys.stderr)
        return set()
    new_journals = set()
    cur_name, cur_added = None, None

    def flush():
        if cur_name and cur_added:
            try:
                added = datetime.strptime(cur_added, "%Y-%m-%d").date()
            except ValueError:
                return
            if 0 <= (today - added).days <= since_days:
                new_journals.add(cur_name)

    for line in text.splitlines():
        if re.match(r"^  - key: ", line):
            flush()
            cur_name, cur_added = None, None
        m = re.match(r"^    journal: (.+)$", line)
        if m:
            cur_name = m.group(1).strip()
        m = re.match(r"^    added_on: (\d{4}-\d{2}-\d{2})\s*$", line)
        if m:
            cur_added = m.group(1)
    flush()
    return new_journals


def fetch_oa_by_doi(dois):
    """Per-DOI Unpaywall lookup: DOI (lowercased) -> (is_open_access, pdf_url).

    A DOI Unpaywall has no record for yet (HTTP 404, typically 1-2 days
    after publication) is absent from the map; callers keep
    pdf_url/is_open_access null for it (unknown, not closed). Any other
    failure skips that DOI and continues with the rest. Never fabricates
    OA data. Stdlib only. ~0.3 s spacing between requests.
    """
    import time

    out = {}
    uniq = [d for d in dict.fromkeys((d or "").strip() for d in dois) if d]
    for doi in uniq:
        url = ("https://api.unpaywall.org/v2/"
               + urllib.parse.quote(doi, safe="")
               + "?email=" + urllib.parse.quote(UNPAYWALL_EMAIL, safe=""))
        req = urllib.request.Request(url, headers={"User-Agent": "JournalWatchFeed/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"Unpaywall {doi}: HTTP {e.code}; leaving OA fields null", file=sys.stderr)
            time.sleep(UNPAYWALL_SLEEP)
            continue
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"Unpaywall {doi}: {e}; leaving OA fields null", file=sys.stderr)
            time.sleep(UNPAYWALL_SLEEP)
            continue
        best = data.get("best_oa_location") or {}
        pdf = best.get("pdf_url") or best.get("url_for_pdf")
        is_oa = data.get("is_oa")
        if pdf and is_oa is None:
            is_oa = True
        out[doi.lower()] = (is_oa, pdf)
        time.sleep(UNPAYWALL_SLEEP)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=3,
                    help="rolling window in days (default 3, matches backfill)")
    ap.add_argument("--out", default="feed.json")
    ap.add_argument("--db", default="data/journal_watch.db")
    ap.add_argument("--config", default="journal-watch/config/journals.yaml",
                    help="journals.yaml path (for the new-journal exception)")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"db not found: {db_path}", file=sys.stderr)
        return 1

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    # Same window, as a calendar date, for published_online. The discovered_at
    # window alone is not enough: in a fresh DB (e.g. a GitHub Actions run)
    # every paper is "discovered now", so months-old RSS backlog (Joule's
    # feed lists papers back to May) would all enter the feed. Bounding by
    # publication date keeps the rolling window honest in both cases; on the
    # persistent VM DB the two filters agree (verified: all 28 papers in the
    # 2026-11-12 VM feed pass both). Papers with no published_online fall
    # back to the discovered_at window only.
    # Exception (2026-11-13): journals added within the last 7 days may
    # contribute papers published up to 45 days ago, provided they were
    # discovered in the rolling window -- the one-time catch-up when a
    # journal joins monitoring. Steady-state journals are unaffected, so
    # the Joule backlog stays out.
    pub_cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
    pub_cap = (datetime.now(timezone.utc) - timedelta(days=CATCHUP_PUB_CAP_DAYS)).date().isoformat()
    config_path = args.config
    if not Path(config_path).exists():
        alt = Path("config/journals.yaml")
        config_path = str(alt) if alt.exists() else config_path
    new_journals = load_new_journals(config_path)
    if new_journals:
        print(f"new-journal exception active for: {sorted(new_journals)}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    if new_journals:
        placeholders = ",".join("?" for _ in new_journals)
        rows = con.execute(
            f"""
            SELECT journal, title, doi, url, authors, abstract, article_type,
                   published_online, discovered_at
            FROM papers
            WHERE status = 'notified' AND discovered_at >= ?
              AND (published_online IS NULL OR substr(published_online, 1, 10) >= ?
                   OR (journal IN ({placeholders})
                       AND (published_online IS NULL OR substr(published_online, 1, 10) >= ?)))
            ORDER BY discovered_at DESC
            """,
            (cutoff, pub_cutoff, *sorted(new_journals), pub_cap),
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT journal, title, doi, url, authors, abstract, article_type,
                   published_online, discovered_at
            FROM papers
            WHERE status = 'notified' AND discovered_at >= ?
              AND (published_online IS NULL OR substr(published_online, 1, 10) >= ?)
            ORDER BY discovered_at DESC
            """,
            (cutoff, pub_cutoff),
        ).fetchall()
    con.close()

    # Dedup by DOI (fallback: normalized title), keep newest occurrence.
    seen = set()
    papers = []
    for r in rows:
        key = (r["doi"] or "").strip().lower() or (r["title"] or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        papers.append({
            "journal": r["journal"],
            "title": clean_title(r["title"]),
            # Brief-compatible aliases (see feed-contract.md): pub_date is the
            # date part of published_online; abstract_url mirrors url.
            # pdf_url/is_open_access are filled from Unpaywall below; a DOI
            # Unpaywall has no record for yet stays null (unknown, not closed).
            "pub_date": (r["published_online"] or "")[:10] or None,
            "doi": r["doi"],
            "url": r["url"],
            "abstract_url": r["url"],
            "pdf_url": None,
            "is_open_access": None,
            "authors": parse_authors(r["authors"]),
            "abstract": r["abstract"],
            "article_type": r["article_type"],
            "published_online": r["published_online"],
            "discovered_at": r["discovered_at"],
        })

    # OA enrichment (Unpaywall, per DOI; failure-tolerant).
    oa_map = fetch_oa_by_doi([p["doi"] for p in papers])
    n_oa = n_open = n_pdf = 0
    for p in papers:
        hit = oa_map.get((p["doi"] or "").strip().lower())
        if hit is None:
            continue
        is_oa, pdf = hit
        if is_oa is not None:
            p["is_open_access"] = is_oa
            n_oa += 1
            if is_oa:
                n_open += 1
        if pdf:
            p["pdf_url"] = pdf
            n_pdf += 1
    print(f"OA (Unpaywall): {n_oa}/{len(papers)} with OA status ({n_open} open), {n_pdf} with PDF URL")

    now = datetime.now(timezone.utc)
    feed = {
        "feed_date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "window_days": args.days,
        "count": len(papers),
        "papers": papers,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also write the dated snapshot the brief originally specified, so the
    # App can use either the rolling feed.json or feed/daily-YYYY-MM-DD.json.
    daily = out.parent / f"daily-{now.date().isoformat()}.json"
    if daily.resolve() != out.resolve():
        daily.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(papers)} papers (last {args.days}d, notified) -> {out} (+ {daily.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
