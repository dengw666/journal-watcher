import requests, logging, time
from datetime import datetime, timedelta, timezone
from src.models import PaperCandidate
from src.normalize import normalize_doi, normalize_date, parse_iso, clean_html

logger = logging.getLogger(__name__)
BASE = "https://api.crossref.org"
PARSER = "crossref_v1"

def _best_date(item: dict) -> datetime | None:
    for key in ('published-online', 'published-print', 'issued', 'created'):
        parts = item.get(key, {}).get('date-parts')
        if parts:
            dt = parse_iso(normalize_date(parts))
            if dt: return dt
    return None

def parse_item(item: dict, journal: str = "Unknown", publisher: str = "") -> PaperCandidate | None:
    title_list = item.get('title', [])
    title = title_list[0] if title_list else ''
    if not title: return None
    doi = normalize_doi(item.get('DOI', ''))
    url = f"https://doi.org/{item['DOI']}" if item.get('DOI') else ''
    authors = None
    if item.get('author'):
        authors = [f"{a.get('given','')} {a.get('family','')}".strip() for a in item['author']]
        authors = [a for a in authors if a] or None
    abstract = clean_html(item.get('abstract'))
    return PaperCandidate(title=title, url=url, journal=journal, publisher=publisher,
        source_type='crossref', discovered_at=datetime.now(timezone.utc),
        doi=doi, authors=authors, abstract=abstract, article_type=item.get('type',''),
        published_online=_best_date(item), parser_name=PARSER)

def fetch_and_parse(issn: str, days_back: int = 3, rows: int = 100,
                    mailto: str = "your@example.com",
                    journal_override: str = None,
                    publisher_override: str = None) -> tuple[list[PaperCandidate], str | None]:
    """Returns (papers, error)."""
    since = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        resp = requests.get(f"{BASE}/journals/{issn}/works",
            params={'filter': f'from-index-date:{since}', 'rows': rows,
                    'sort': 'indexed', 'order': 'desc', 'mailto': mailto},
            headers={'User-Agent': f'JournalWatch/1.0 (mailto:{mailto})'}, timeout=30)
        resp.raise_for_status()
        data = resp.json().get('message', {})
        total = data.get('total-results', 0)
        items = data.get('items', [])
        if total > rows:
            logger.warning("Crossref ISSN %s: total=%d > rows=%d, truncated", issn, total, rows)
    except requests.RequestException as e:
        logger.error("Crossref %s: %s", issn, e); return [], str(e)
    finally: time.sleep(1)
    papers = [p for item in items
              if (p := parse_item(item,
                  journal=journal_override or item.get('container-title', ['Unknown'])[0],
                  publisher=publisher_override or item.get('publisher', ''))) is not None]
    return papers, None
