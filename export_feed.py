#!/usr/bin/env python3
"""Export a rolling JSON feed of pushed journal-watch papers for the iOS app.

Reads data/journal_watch.db and writes feed.json containing papers that were
pushed (status='notified') within the last N days, deduplicated by DOI,
newest first. The app reads this file via raw.githubusercontent.com once it
is committed to the repo; nothing phones home and no LLM is involved in
search (RSS + Crossref + keyword filter already happened upstream).

Usage:
    python3 export_feed.py [--days 3] [--out feed.json] [--db data/journal_watch.db]
"""
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=3,
                    help="rolling window in days (default 3, matches backfill)")
    ap.add_argument("--out", default="feed.json")
    ap.add_argument("--db", default="data/journal_watch.db")
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
    pub_cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
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
            # pdf_url/is_open_access stay null until an OA lookup (e.g.
            # Unpaywall) is wired in — the DB has no OA data, so we never
            # fabricate either field.
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
