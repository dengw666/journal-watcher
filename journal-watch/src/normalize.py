import re, unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote, urlparse, urlunparse
from dateutil import parser as dateutil_parser
from bs4 import BeautifulSoup

DOI_RE = re.compile(r'(10\.\d{4,9}/[^\s]+)', re.IGNORECASE)
DASH_RE = re.compile(r'[\u2010\u2011\u2012\u2013\u2014\u2015\uFE58\uFE63\uFF0D]')
PUNCT_RE = re.compile(r'[/(),:;\[\]{}]')


def normalize_doi(raw: str | None) -> str | None:
    if not raw: return None
    m = DOI_RE.search(unquote(raw.strip()))
    return m.group(1).rstrip('.,;:)').lower() if m else None


def normalize_date(date_input) -> str | None:
    if date_input is None: return None
    if hasattr(date_input, 'tm_year'):
        try: return datetime(*date_input[:6], tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        except (ValueError, TypeError): return None
    if isinstance(date_input, (list, tuple)):
        try:
            p = date_input[0] if isinstance(date_input[0], (list, tuple)) else date_input
            return datetime(int(p[0]), int(p[1]) if len(p)>1 else 1,
                            int(p[2]) if len(p)>2 else 1, tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        except (ValueError, TypeError, IndexError): return None
    if isinstance(date_input, str) and date_input.strip():
        try:
            dt = dateutil_parser.parse(date_input)
            dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        except (ValueError, OverflowError): return None
    return None


def parse_iso(s: str | None) -> datetime | None:
    if not s: return None
    try: return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except (ValueError, TypeError): return None


def to_iso(dt: datetime | None) -> str | None:
    if not dt: return None
    dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def days_ago_iso(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime('%Y-%m-%dT%H:%M:%SZ')


def normalize_title(title: str) -> str:
    if not title: return ""
    title = unicodedata.normalize('NFKD', title).lower()
    title = BeautifulSoup(title, "lxml").get_text(" ", strip=True)
    title = re.sub(r'[^a-z0-9\s]', '', title)
    return re.sub(r'\s+', ' ', title).strip()


def clean_html(html: str | None) -> str | None:
    """HTML -> plain text. Returns None only for blank/symbol-only content."""
    if not html: return None
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    if not text or not re.search(r'[a-zA-Z0-9]', text): return None
    return text


def normalize_dashes(text: str) -> str:
    return DASH_RE.sub('-', text)


def clean_for_match(text: str) -> str:
    """dash normalize + punctuation cleanup + lower"""
    text = normalize_dashes(text)
    text = PUNCT_RE.sub(' ', text)
    return re.sub(r'\s+', ' ', text).lower()


def normalize_url(url: str | None) -> str | None:
    """URL normalization: add scheme, strip www., default ports, query/fragment/trailing slash, dx.doi.org->doi.org, merge slashes, DOI path lowercase"""
    if not url or not url.strip(): return None
    raw = url.strip()
    work = raw
    if not work.startswith(('http://', 'https://')):
        work = 'https://' + work
    try:
        p = urlparse(work)
        scheme = p.scheme.lower()
        netloc = p.netloc.lower()
        if not netloc: return raw
        if netloc.startswith('www.'): netloc = netloc[4:]
        netloc = netloc.replace('dx.doi.org', 'doi.org')
        if netloc.endswith(':80') and scheme == 'http': netloc = netloc[:-3]
        if netloc.endswith(':443') and scheme == 'https': netloc = netloc[:-4]
        path = re.sub(r'/+', '/', p.path).rstrip('/')
        if netloc == 'doi.org': path = path.lower()
        return urlunparse((scheme, netloc, path, '', '', ''))
    except Exception: return raw
