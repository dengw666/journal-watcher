import re, logging
from src.models import PaperCandidate
from src.config_loader import load_topics
from src.normalize import clean_for_match

logger = logging.getLogger(__name__)
_cache = None

def _cfg():
    global _cache
    if _cache is None:
        raw = load_topics()
        _cache = {
            'include': [(kw, clean_for_match(kw)) for kw in raw.get('include_keywords', [])],
            'exclude': [(kw, clean_for_match(kw)) for kw in raw.get('exclude_keywords', [])],
        }
    return _cache

def _match(text_lower: str, kw_lower: str) -> bool:
    kw = kw_lower.strip()
    if not text_lower or not kw: return False
    if len(kw) <= 3:
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text_lower))
    return kw in text_lower

# Journals that skip keyword filtering — all papers are included
PASSTHROUGH_JOURNALS = {'Nature Energy'}

def filter_paper(paper: PaperCandidate, config: dict = None) -> tuple[bool, list[str]]:
    if paper.journal in PASSTHROUGH_JOURNALS:
        return True, ['(全收)']

    if config:
        text = clean_for_match(' '.join(filter(None, [paper.title, paper.abstract,
            ' '.join(paper.raw_tags or []), paper.journal, paper.article_type])))
        for kw in config.get('exclude_keywords', []):
            if _match(text, clean_for_match(kw)): return False, []
        matched = [kw for kw in config.get('include_keywords', []) if _match(text, clean_for_match(kw))]
        return (True, matched) if matched else (False, [])

    cfg = _cfg()
    text = clean_for_match(' '.join(filter(None, [paper.title, paper.abstract,
        ' '.join(paper.raw_tags or []), paper.journal, paper.article_type])))
    for _, kw_c in cfg['exclude']:
        if _match(text, kw_c): return False, []
    matched = [kw_raw for kw_raw, kw_c in cfg['include'] if _match(text, kw_c)]
    return (True, matched) if matched else (False, [])
