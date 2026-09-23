import json
from pathlib import Path
import feedparser, pytest
FIX = Path(__file__).parent / "fixtures"
RSS = [("nature_energy.xml","Nature Energy","nature"),("science.xml","Science","aaas"),
       ("jacs_asap.xml","JACS","acs"),("joule_inpress.xml","Joule","cell")]

@pytest.mark.parametrize("fixture,journal,publisher", RSS, ids=[c[0] for c in RSS])
def test_rss(fixture, journal, publisher):
    path = FIX / fixture
    if not path.exists(): pytest.skip(f"{fixture} missing")
    from src.parsers.rss_parser import parse_entry
    feed = feedparser.parse(path.read_bytes())
    assert feed.entries
    p = parse_entry(feed.entries[0], journal, publisher)
    assert p and p.title and p.url and p.journal == journal
    if p.doi: assert p.doi == p.doi.lower() and not p.doi.startswith('http')

def test_chemrxiv():
    path = FIX / "chemrxiv_api.json"
    if not path.exists(): pytest.skip("missing")
    from src.sources.chemrxiv import parse_item
    data = json.loads(path.read_text(encoding='utf-8'))
    item = data.get('itemHits',[{}])[0].get('item',{})
    p = parse_item(item)
    assert p and p.title and p.journal == 'ChemRxiv'

def test_crossref():
    path = FIX / "crossref_nature_energy.json"
    if not path.exists(): pytest.skip("missing")
    from src.sources.crossref import parse_item
    items = json.loads(path.read_text(encoding='utf-8')).get('message',{}).get('items',[])
    assert items
    p = parse_item(items[0], journal='Nature Energy', publisher='nature')
    assert p and p.title and p.journal == 'Nature Energy'
