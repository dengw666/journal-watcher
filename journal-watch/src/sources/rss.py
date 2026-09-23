import feedparser, requests, logging, time
logger = logging.getLogger(__name__)
_UA = 'JournalWatch/1.0 (academic-monitoring; mailto:your@email.com)'

def fetch_rss(url: str, timeout: int = 15) -> dict:
    try:
        resp = requests.get(url, timeout=timeout,
            headers={'User-Agent': _UA, 'Accept': 'application/rss+xml, application/xml, text/xml'})
        resp.raise_for_status()
        return dict(entries=feedparser.parse(resp.content).entries, status=resp.status_code, error=None)
    except requests.RequestException as e:
        logger.error("RSS %s: %s", url, e)
        return dict(entries=[], status=0, error=str(e))
    finally: time.sleep(1)
