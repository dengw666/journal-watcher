"""Enrich papers with abstracts from Springer Nature API and DOI landing pages."""
import requests, re, logging, time
from bs4 import BeautifulSoup
from src.db import get_connection
from src.normalize import utcnow_iso

logger = logging.getLogger(__name__)
_UA = 'JournalWatch/1.0 (academic-monitoring)'


def _springer_nature_abstract(doi: str, api_key: str) -> str | None:
    """Springer Nature Metadata API (free, needs API key)."""
    try:
        resp = requests.get(
            'https://api.springernature.com/meta/v2/json',
            params={'q': f'doi:{doi}', 'api_key': api_key},
            headers={'User-Agent': _UA}, timeout=15)
        resp.raise_for_status()
        records = resp.json().get('records', [])
        if records:
            abstract = records[0].get('abstract', '').strip()
            if abstract and len(abstract) > 20:
                return abstract
    except Exception as e:
        logger.debug("Springer API %s: %s", doi, e)
    finally:
        time.sleep(0.5)
    return None


def _scrape_doi_landing(doi: str) -> str | None:
    """Scrape meta description from DOI landing page (universal fallback)."""
    url = f'https://doi.org/{doi}'
    try:
        resp = requests.get(url, timeout=10, headers={
            'User-Agent': _UA,
            'Accept': 'text/html',
        }, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        # Try multiple meta tag patterns
        for selector in [
            {'name': 'description'},
            {'property': 'og:description'},
            {'name': 'DC.description'},
            {'name': 'citation_abstract'},
        ]:
            tag = soup.find('meta', attrs=selector)
            if tag and tag.get('content', '').strip():
                text = tag['content'].strip()
                # Skip if too short or just a journal name
                if len(text) > 30 and not text.startswith('Journal of'):
                    return text
        # Try <div class="c-article-section__content"> (Nature)
        for cls in ['c-article-section__content', 'abstractSection', 'hlFld-Abstract']:
            div = soup.find('div', class_=cls)
            if div:
                text = div.get_text(' ', strip=True)
                if len(text) > 30:
                    return text[:2000]
    except Exception as e:
        logger.debug("Scrape DOI %s: %s", doi, e)
    finally:
        time.sleep(1)
    return None


def enrich_missing_abstracts(springer_api_key: str | None = None, limit: int = 50):
    """Find papers without abstracts and try to fill them in."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, doi, publisher, abstract FROM papers
        WHERE doi IS NOT NULL
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    # Filter: no abstract, or placeholder-quality abstract
    def _is_placeholder(ab: str | None) -> bool:
        if not ab: return True
        ab = ab.strip()
        if len(ab) < 80: return True
        # "Nature, Published online: ..." or "Journal of the ... DOI: ..."
        lower = ab.lower()
        if 'published online:' in lower and 'doi:' in lower: return True
        if lower.startswith('journal of') and 'doi:' in lower: return True
        return False
    rows = [(pid, doi, pub) for pid, doi, pub, ab in rows if _is_placeholder(ab)]

    if not rows:
        return 0

    updated = 0
    for pid, doi, publisher in rows:
        abstract = None
        # Try Springer Nature API first for Nature-family journals
        if springer_api_key and publisher == 'nature':
            abstract = _springer_nature_abstract(doi, springer_api_key)
            if abstract:
                logger.info("Springer API enriched: %s", doi)

        # Fallback: scrape DOI landing page
        if not abstract:
            abstract = _scrape_doi_landing(doi)
            if abstract:
                logger.info("DOI scrape enriched: %s", doi)

        if abstract:
            conn = get_connection()
            conn.execute("UPDATE papers SET abstract=?, updated_at=? WHERE id=?",
                         (abstract, utcnow_iso(), pid))
            conn.commit()
            conn.close()
            updated += 1

    return updated
