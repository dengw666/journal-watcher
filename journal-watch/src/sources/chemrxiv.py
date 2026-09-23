import requests, logging, time
from datetime import datetime, timedelta, timezone
from src.models import PaperCandidate
from src.normalize import normalize_date, parse_iso, clean_html

logger = logging.getLogger(__name__)
API = "https://chemrxiv.org/engage/chemrxiv/public-api/v1/items"
PARSER = "chemrxiv_v1"

def parse_item(item: dict) -> PaperCandidate | None:
    title = item.get('title', '').strip()
    if not title: return None
    doi = item.get('doi') or None
    url = f"https://doi.org/{doi}" if doi else item.get('url', '')
    authors = None
    if item.get('authors'):
        authors = [f"{a.get('firstName','')} {a.get('lastName','')}".strip() for a in item['authors']]
        authors = [a for a in authors if a] or None
    abstract = clean_html(item.get('abstract'))
    pub_date = parse_iso(normalize_date(item.get('publishedDate') or item.get('statusDate')))
    cats = [c.get('name','') for c in item.get('categories',[]) if c.get('name')]
    return PaperCandidate(title=title, url=url, journal='ChemRxiv', publisher='chemrxiv',
        source_type='api', discovered_at=datetime.now(timezone.utc),
        doi=doi, authors=authors, abstract=abstract, published_online=pub_date,
        raw_tags=cats or None, parser_name=PARSER)

def fetch_and_parse(days_back: int = 2, limit: int = 50) -> tuple[list[PaperCandidate], str | None]:
    """Returns (papers, error). error is None on success."""
    since = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00.000Z')
    try:
        resp = requests.get(API, timeout=10, headers={'User-Agent': 'JournalWatch/1.0'},
            params={'limit': limit, 'skip': 0, 'sort': 'PUBLISHED_DATE_DESC', 'searchDateFrom': since})
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("ChemRxiv (%s): %s", API, e); return [], str(e)
    finally: time.sleep(1)
    papers = [p for hit in resp.json().get('itemHits', [])
              if (p := parse_item(hit.get('item', {}))) is not None]
    return papers, None
