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

# Generic (polysemous) keywords: a single match is not enough evidence —
# these words also appear in biology, physics and sensing papers.
# A paper passes if any strong (non-generic) keyword matches, or at least
# two generic keywords match. (2026-11-06: backfill surfaced many
# single-generic-keyword false positives, e.g. "electrolyte" in an
# Alzheimer's paper, "cathode" in an X-ray laser paper.)
GENERIC_KEYWORDS = {
    'anode', 'cathode', 'electrode', 'current collector', 'separator',
    'electrolyte', 'catholyte', 'solvation', 'desolvation', 'interphase',
    'electrochemical', 'charge transfer', 'impedance', 'energy storage',
    'stripping', 'plating/stripping', 'dendritic', 'ionic liquid',
    'intercalation',
}

def _include_pass(text: str, include_pairs) -> tuple[bool, list[str]]:
    """include_pairs: iterable of (raw_kw, cleaned_kw). Returns (passes, matched)."""
    generic_clean = {clean_for_match(g) for g in GENERIC_KEYWORDS}
    matched = [raw for raw, c in include_pairs if _match(text, c)]
    strong = [raw for raw, c in include_pairs if c not in generic_clean and _match(text, c)]
    generic = [raw for raw, c in include_pairs if c in generic_clean and _match(text, c)]
    return (bool(strong) or len(generic) >= 2), matched

def filter_paper(paper: PaperCandidate, config: dict = None) -> tuple[bool, list[str]]:
    if paper.journal in PASSTHROUGH_JOURNALS:
        return True, ['(全收)']

    if config:
        text = clean_for_match(' '.join(filter(None, [paper.title, paper.abstract,
            ' '.join(paper.raw_tags or []), paper.journal, paper.article_type])))
        for kw in config.get('exclude_keywords', []):
            if _match(text, clean_for_match(kw)): return False, []
        pairs = [(kw, clean_for_match(kw)) for kw in config.get('include_keywords', [])]
        ok, matched = _include_pass(text, pairs)
        return (True, matched) if ok else (False, [])

    cfg = _cfg()
    text = clean_for_match(' '.join(filter(None, [paper.title, paper.abstract,
        ' '.join(paper.raw_tags or []), paper.journal, paper.article_type])))
    for _, kw_c in cfg['exclude']:
        if _match(text, kw_c): return False, []
    ok, matched = _include_pass(text, cfg['include'])
    return (True, matched) if ok else (False, [])
