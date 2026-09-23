import json, pytest
from datetime import datetime, timezone
from src.models import PaperCandidate
from src.db import init_db, store_paper, mark_notified, get_connection


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    import src.db as db_mod
    db_mod.DB_PATH = tmp_path / "test.db"
    init_db()
    yield


def _paper(title="Test battery paper", doi=None, journal="Nature Energy",
           publisher="nature", url="https://example.com/1", abstract=None,
           authors=None, published_online=None):
    return PaperCandidate(title=title, url=url, journal=journal, publisher=publisher,
        source_type='rss', discovered_at=datetime.now(timezone.utc),
        doi=doi, abstract=abstract, authors=authors, published_online=published_online)


class TestStore:
    def test_insert(self):
        assert store_paper(_paper()) == 'inserted'

    def test_doi_dedup(self):
        store_paper(_paper(doi='10.1234/test1'))
        assert store_paper(_paper(doi='10.1234/test1', url='https://other.com')) == 'duplicate'

    def test_title_journal_dedup(self):
        store_paper(_paper(title='Novel electrolyte', url='https://a.com/1'))
        assert store_paper(_paper(title='Novel electrolyte', url='https://a.com/2')) == 'duplicate'

    def test_different_journal(self):
        store_paper(_paper(title='Novel electrolyte', journal='Nature', url='https://nature.com/1'))
        assert store_paper(_paper(title='Novel electrolyte', journal='Science', url='https://science.org/1')) == 'inserted'


class TestBackfill:
    def test_doi_backfill_via_title_match(self):
        """RSS without DOI -> Crossref with DOI -> DOI and abstract backfilled"""
        store_paper(_paper(title='SEI study on lithium', doi=None, url='https://nature.com/1'))
        result = store_paper(
            _paper(title='SEI study on lithium', doi='10.1038/test-sei',
                   url='https://doi.org/10.1038/test-sei', abstract='Good abstract'),
            backfill=True)
        assert result == 'updated'
        conn = get_connection()
        row = conn.execute("SELECT doi, abstract FROM papers WHERE normalized_title LIKE '%sei study%'").fetchone()
        conn.close()
        assert row[0] == '10.1038/test-sei', "DOI should be backfilled"
        assert row[1] == 'Good abstract', "Abstract should be backfilled"

    def test_integrity_error_backfill_recovers(self):
        """URL conflict triggers IntegrityError -> re-find and backfill succeeds"""
        store_paper(_paper(title='A battery study v1', doi=None, url='https://example.com/article'))
        result = store_paper(
            _paper(title='A battery study v1', doi='10.9999/new', url='https://example.com/article',
                   abstract='Recovered abstract'),
            backfill=True)
        assert result == 'updated', f"Expected 'updated' but got '{result}'"
        conn = get_connection()
        row = conn.execute("SELECT doi, abstract FROM papers WHERE url=?",
                          ('https://example.com/article',)).fetchone()
        conn.close()
        assert row[0] == '10.9999/new', "DOI must be backfilled after IntegrityError recovery"
        assert row[1] == 'Recovered abstract', "Abstract must be backfilled"

    def test_no_overwrite_abstract(self):
        store_paper(_paper(doi='10.1234/x', abstract='Original'))
        store_paper(_paper(doi='10.1234/x', abstract='New'), backfill=True)
        conn = get_connection()
        assert conn.execute("SELECT abstract FROM papers WHERE doi='10.1234/x'").fetchone()[0] == 'Original'
        conn.close()

    def test_no_overwrite_authors(self):
        store_paper(_paper(doi='10.1234/y', authors=['Alice']))
        store_paper(_paper(doi='10.1234/y', authors=['Bob']), backfill=True)
        conn = get_connection()
        assert json.loads(conn.execute("SELECT authors FROM papers WHERE doi='10.1234/y'").fetchone()[0]) == ['Alice']
        conn.close()

    def test_no_overwrite_date(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        store_paper(_paper(doi='10.1234/z', published_online=dt1))
        store_paper(_paper(doi='10.1234/z', published_online=datetime(2025, 6, 1, tzinfo=timezone.utc)), backfill=True)
        conn = get_connection()
        assert '2024-01-01' in conn.execute("SELECT published_online FROM papers WHERE doi='10.1234/z'").fetchone()[0]
        conn.close()


class TestMarkNotified:
    def test_precise(self):
        store_paper(_paper(title='Paper A', url='https://a.com'))
        store_paper(_paper(title='Paper B', url='https://b.com'))
        conn = get_connection()
        id_a = conn.execute("SELECT id FROM papers WHERE title='Paper A'").fetchone()[0]
        conn.close()
        mark_notified([id_a])
        conn = get_connection()
        assert conn.execute("SELECT status FROM papers WHERE title='Paper A'").fetchone()[0] == 'notified'
        assert conn.execute("SELECT status FROM papers WHERE title='Paper B'").fetchone()[0] == 'new'
        conn.close()

    def test_dedup_ids(self):
        """Duplicate ids should not error"""
        store_paper(_paper(title='Paper C', url='https://c.com'))
        conn = get_connection()
        id_c = conn.execute("SELECT id FROM papers WHERE title='Paper C'").fetchone()[0]
        conn.close()
        mark_notified([id_c, id_c, id_c])
        conn = get_connection()
        assert conn.execute("SELECT status FROM papers WHERE id=?", (id_c,)).fetchone()[0] == 'notified'
        conn.close()
