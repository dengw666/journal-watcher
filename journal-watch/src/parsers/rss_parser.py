from datetime import datetime, timezone
from src.models import PaperCandidate
from src.normalize import normalize_doi, normalize_date, parse_iso, clean_html

PARSER_NAME = "rss_v1"
_DOI_FIELDS = ['prism_doi', 'dc_identifier', 'id', 'link']

def parse_entry(entry: dict, journal: str, publisher: str) -> PaperCandidate | None:
    title = entry.get('title', '').strip()
    if not title: return None
    link = entry.get('link', '')
    doi = None
    for f in _DOI_FIELDS:
        doi = normalize_doi(entry.get(f, ''))
        if doi: break
    abstract = clean_html(entry.get('summary', ''))
    authors = None
    if 'authors' in entry:
        authors = [a.get('name','') for a in entry['authors'] if a.get('name')]
    elif entry.get('author'): authors = [entry['author']]
    if authors and not any(authors): authors = None
    pub_date = parse_iso(normalize_date(entry.get('published_parsed') or entry.get('updated_parsed')))
    return PaperCandidate(title=title, url=link, journal=journal, publisher=publisher,
        source_type='rss', discovered_at=datetime.now(timezone.utc),
        doi=doi, authors=authors, abstract=abstract, published_online=pub_date, parser_name=PARSER_NAME)
