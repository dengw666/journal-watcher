import sqlite3, json, logging
from pathlib import Path
from src.normalize import normalize_title, normalize_url, to_iso, utcnow_iso

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent.parent / "data" / "journal_watch.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT UNIQUE,
            url TEXT UNIQUE,
            title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            journal TEXT NOT NULL,
            publisher TEXT NOT NULL,
            authors TEXT,
            abstract TEXT,
            article_type TEXT,
            published_online TEXT,
            source_type TEXT,
            parser_name TEXT,
            discovered_at TEXT NOT NULL,
            keywords_matched TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        -- (normalized_title, journal) globally unique: intentionally conservative dedup strategy.
        -- Side effect: same-journal same-title articles (e.g. editorial + correction) merge.
        -- Rare in practice and negligible for daily new-paper discovery.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_title_journal
            ON papers(normalized_title, journal);
        CREATE INDEX IF NOT EXISTS idx_status ON papers(status);
        CREATE INDEX IF NOT EXISTS idx_discovered ON papers(discovered_at);
    """)
    conn.commit(); conn.close()


def _find_existing(conn, doi: str | None, norm_title: str, journal: str,
                   norm_url: str | None = None) -> tuple | None:
    """DOI -> title+journal -> URL"""
    if doi:
        row = conn.execute("SELECT id,doi,abstract,authors,published_online FROM papers WHERE doi=?", (doi,)).fetchone()
        if row: return row
    if norm_title:
        row = conn.execute("SELECT id,doi,abstract,authors,published_online FROM papers WHERE normalized_title=? AND journal=?",
                           (norm_title, journal)).fetchone()
        if row: return row
    if norm_url:
        row = conn.execute("SELECT id,doi,abstract,authors,published_online FROM papers WHERE url=?", (norm_url,)).fetchone()
        if row: return row
    return None


def _do_backfill(conn, row, paper, now: str) -> str:
    pid, ex_doi, ex_abs, ex_auth, ex_date = row
    updates, params = [], []
    if not ex_doi and paper.doi:
        updates.append("doi=?"); params.append(paper.doi)
    if not ex_abs and paper.abstract:
        updates.append("abstract=?"); params.append(paper.abstract)
    if not ex_auth and paper.authors:
        updates.append("authors=?"); params.append(json.dumps(paper.authors, ensure_ascii=False))
    if not ex_date and paper.published_online:
        updates.append("published_online=?"); params.append(to_iso(paper.published_online))
    if updates:
        updates.append("updated_at=?"); params.append(now); params.append(pid)
        conn.execute(f"UPDATE papers SET {','.join(updates)} WHERE id=?", params)
        conn.commit(); return 'updated'
    return 'duplicate'


def store_paper(paper, backfill: bool = False) -> str:
    conn = get_connection()
    norm_title = normalize_title(paper.title)
    norm_url = normalize_url(paper.url)
    now = utcnow_iso()
    try:
        row = _find_existing(conn, paper.doi, norm_title, paper.journal, norm_url)
        if not row:
            try:
                conn.execute("""
                    INSERT INTO papers
                        (doi,url,title,normalized_title,journal,publisher,
                         authors,abstract,article_type,published_online,
                         source_type,parser_name,discovered_at,keywords_matched,
                         status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new',?,?)
                """, (paper.doi, norm_url, paper.title, norm_title,
                      paper.journal, paper.publisher,
                      json.dumps(paper.authors, ensure_ascii=False) if paper.authors else None,
                      paper.abstract, paper.article_type, to_iso(paper.published_online),
                      paper.source_type, paper.parser_name, to_iso(paper.discovered_at),
                      json.dumps(paper.keywords_matched, ensure_ascii=False) if paper.keywords_matched else None,
                      now, now))
                conn.commit(); return 'inserted'
            except sqlite3.IntegrityError:
                row = _find_existing(conn, paper.doi, norm_title, paper.journal, norm_url)
                if row and backfill: return _do_backfill(conn, row, paper, now)
                return 'duplicate'
        if not backfill: return 'duplicate'
        return _do_backfill(conn, row, paper, now)
    except Exception as e:
        logger.error("store_paper: %s — %s", paper.doi or paper.title[:40], e); return 'error'
    finally: conn.close()


def mark_notified(paper_ids: list[int]):
    if not paper_ids: return
    ids = sorted(set(paper_ids))
    conn = get_connection()
    ph = ','.join('?' * len(ids))
    conn.execute(f"UPDATE papers SET status='notified',updated_at=? WHERE id IN ({ph})",
                 [utcnow_iso()] + ids)
    conn.commit(); conn.close()
