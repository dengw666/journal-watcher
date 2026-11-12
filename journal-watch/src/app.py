import logging
from datetime import datetime, timezone, timedelta
from src.db import init_db, store_paper
from src.config_loader import load_journals, load_topics
from src.sources.rss import fetch_rss
from src.sources import chemrxiv, crossref
from src.parsers.rss_parser import parse_entry
from src.filter import filter_paper
from src.enrich import enrich_missing_abstracts

logger = logging.getLogger(__name__)

def _within_days(paper, days_back: int) -> bool:
    """RSS 里出现的论文都应入库，不按 published_online 过滤。
    published_online 代表发表日，周刊/月刊的论文可能在 feed 里停留多天但发表日已"过期"。
    去重由 DB 的唯一约束保证，展示窗口由 digest 的 discovered_at 控制。"""
    return True

def run_scan(days_back: int = 2, verbose: bool = True) -> dict:
    """T+0 main scan. --days is rolling window (past N*24h)."""
    init_db()
    cfg, tcfg = load_journals(), load_topics()
    s = {'fetched': 0, 'candidates': 0, 'new': 0, 'dup': 0, 'filtered': 0, 'errors': []}
    for jcfg in cfg.get('journals', []):
        jn, pub = jcfg['journal'], jcfg['publisher']
        if verbose: print(f"\n--- {jn} ---")
        for src in jcfg.get('sources', []):
            try:
                raw_count = 0
                cands = []
                if src['type'] == 'rss':
                    r = fetch_rss(src['url'])
                    if r['error']:
                        s['errors'].append(f"{jn} ({src['url']}): {r['error']}")
                        if verbose: print(f"  x {r['error']}"); continue
                    raw_count = len(r['entries'])
                    for e in r['entries']:
                        p = parse_entry(e, jn, pub)
                        if p and _within_days(p, days_back): cands.append(p)
                    if verbose: print(f"  RSS: {raw_count} fetched, {len(cands)} in window")
                elif src['type'] == 'chemrxiv_api':
                    papers, err = chemrxiv.fetch_and_parse(days_back=days_back)
                    if err:
                        s['errors'].append(f"{jn} ({src['url']}): {err}")
                        if verbose: print(f"  x {err}")
                    raw_count = len(papers)
                    cands = papers
                    if verbose: print(f"  API: {raw_count} items")

                s['fetched'] += raw_count
                s['candidates'] += len(cands)
                for paper in cands:
                    ok, kws = filter_paper(paper, tcfg)
                    if not ok: s['filtered'] += 1; continue
                    paper.keywords_matched = kws
                    r = store_paper(paper, backfill=False)
                    if r == 'inserted':
                        s['new'] += 1
                        if verbose: print(f"  + {paper.title[:65]}...")
                    elif r == 'duplicate': s['dup'] += 1
            except Exception as e:
                s['errors'].append(f"{jn} ({src.get('url','')}): {e}")
                if verbose: print(f"  x {e}")
    if verbose:
        print(f"\n{'='*50}")
        print(f"Scan  fetched:{s['fetched']} candidates:{s['candidates']} "
              f"filtered:{s['filtered']} new:{s['new']} dup:{s['dup']} err:{len(s['errors'])}")
        for e in s['errors']: print(f"  ERR: {e}")

    # Enrich missing abstracts (skip in quiet mode to keep scan fast)
    if s['new'] > 0 and verbose:
        springer_key = cfg.get('springer_nature', {}).get('api_key')
        print(f"\n--- 补充摘要 ---")
        enriched = enrich_missing_abstracts(springer_api_key=springer_key, limit=min(s['new'], 10))
        print(f"  补充了 {enriched} 篇摘要")
        s['enriched'] = enriched

    return s

def run_backfill(days_back: int = 3, verbose: bool = True) -> dict:
    """T+1/T+2 Crossref backfill. --days is rolling window."""
    init_db()
    cfg, tcfg = load_journals(), load_topics()
    xcfg = cfg.get('crossref', {})
    if not xcfg.get('enabled'):
        if verbose: print("Crossref disabled."); return {}
    mailto = xcfg.get('mailto', 'your@example.com')
    s = {'fetched': 0, 'updated': 0, 'new': 0, 'dup': 0, 'filtered': 0, 'errors': []}
    if verbose: print(f"\n=== Crossref backfill ({days_back}d) ===\n")
    for jcfg in cfg.get('journals', []):
        issn = jcfg.get('issn')
        if not issn: continue
        jn, pub = jcfg['journal'], jcfg['publisher']
        try:
            papers, err = crossref.fetch_and_parse(issn, days_back=days_back, rows=500, mailto=mailto,
                journal_override=jn, publisher_override=pub)
            if err:
                s['errors'].append(f"{jn}: {err}")
                if verbose: print(f"  x {jn}: {err}")
                continue
            s['fetched'] += len(papers)
            if verbose: print(f"  {jn}: {len(papers)}")
            for paper in papers:
                ok, kws = filter_paper(paper, tcfg)
                if not ok: s['filtered'] += 1; continue
                paper.keywords_matched = kws
                r = store_paper(paper, backfill=True)
                if r == 'updated': s['updated'] += 1; verbose and print(f"    ^ {paper.title[:55]}...")
                elif r == 'inserted': s['new'] += 1; verbose and print(f"    + {paper.title[:55]}...")
                else: s['dup'] += 1
        except Exception as e:
            s['errors'].append(f"{jn}: {e}")
            if verbose: print(f"  x {jn}: {e}")
    if verbose:
        print(f"\n{'='*50}")
        print(f"Backfill  fetched:{s['fetched']} filtered:{s['filtered']} "
              f"updated:{s['updated']} new:{s['new']} dup:{s['dup']} err:{len(s['errors'])}")
    return s
