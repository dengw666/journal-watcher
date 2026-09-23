from src.normalize import *
def test_doi():
    assert normalize_doi('https://doi.org/10.1038/s41586-024-07891-2')=='10.1038/s41586-024-07891-2'
    assert normalize_doi('Https://doi.org/10.1000/xyz')=='10.1000/xyz'
    assert normalize_doi(None) is None
def test_html():
    assert clean_html('<p>Hi &amp; <b>world</b></p>')=='Hi & world'
    assert clean_html('Review.') is not None  # short but has letters
    assert clean_html('   ') is None
    assert clean_html(None) is None
def test_dashes(): assert normalize_dashes('Li\u2013ion')=='Li-ion'
def test_url():
    assert normalize_url('www.nature.com/articles/xxx/')=='https://nature.com/articles/xxx'
    assert normalize_url('dx.doi.org/10.1038/x?ref=rss')=='https://doi.org/10.1038/x'
    assert normalize_url('https://example.com:443/p//q/')=='https://example.com/p/q'
    assert normalize_url('https://doi.org/10.1038/ABC123')=='https://doi.org/10.1038/abc123'
    assert normalize_url(None) is None
def test_clean_for_match():
    r = clean_for_match('Li-ion/SEI(test)')
    assert 'sei' in r and 'li-ion' in r
