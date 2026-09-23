from datetime import datetime, timezone
from src.models import PaperCandidate
from src.filter import filter_paper
def _p(title, journal="Nature", abstract=None, article_type=None):
    return PaperCandidate(title=title, url='', journal=journal, publisher='test',
        source_type='rss', discovered_at=datetime.now(timezone.utc), abstract=abstract, article_type=article_type)
def test_battery(): assert filter_paper(_p('lithium metal battery'))[0]
def test_solar(): assert not filter_paper(_p('Perovskite solar cell'))[0]
def test_nature_energy_passthrough(): assert filter_paper(_p('Energy policy', journal='Nature Energy'))[0]
def test_no_auto_pass(): assert not filter_paper(_p('Energy policy', journal='Science'))[0]
def test_with_kw(): assert filter_paper(_p('Solid-state battery', journal='Nature Energy'))[0]
def test_exclude_wins(): assert not filter_paper(_p('Photoelectrochemical lithium battery'))[0]
def test_dash(): assert filter_paper(_p('Li\u2013ion battery'))[0]
def test_parens(): assert filter_paper(_p('Study of (SEI) formation'))[0]
