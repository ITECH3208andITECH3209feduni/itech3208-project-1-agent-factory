# tests/api/test_amazon_dedicated_endpoint.py
# PROJ-174: tests for POST /amazon endpoint
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.web_ui.main import app

client = TestClient(app)


def _mock_envelope(success=True, results=None, summary='', error='', metadata=None):
    return {
        'success':  success,
        'results':  results or [],
        'summary':  summary,
        'error':    error,
        'metadata': metadata or {},
    }


class _FakeCard:
    def __init__(self, title='X', score=50):
        self.title = title
        self.score = score
    def to_dict(self):
        return {'title': self.title, 'score': self.score}


def test_amazon_returns_cards_on_success():
    cards = [_FakeCard('A', 80), _FakeCard('B', 60)]
    fake = _mock_envelope(success=True, results=cards, summary='Found 2.')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'wireless headphones'})

    assert r.status_code == 200
    data = r.json()
    assert data['type'] == 'amazon'
    assert data['total'] == 2
    assert len(data['cards']) == 2
    assert data['cards'][0]['title'] == 'A'
    assert data['response'] == 'Found 2.'
    assert data['error'] == ''


def test_amazon_always_returns_type_amazon():
    fake = _mock_envelope(success=False, results=[], error='503 from Amazon')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'anything'})

    assert r.status_code == 200
    assert r.json()['type'] == 'amazon'


def test_amazon_empty_cards_on_failure_with_error():
    fake = _mock_envelope(success=False, results=[], error='scraper exploded')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'anything'})

    data = r.json()
    assert data['cards'] == []
    assert data['total'] == 0
    assert 'scraper exploded' in data['error']


def test_amazon_response_text_non_empty_when_no_summary():
    cards = [_FakeCard('C', 70)]
    fake = _mock_envelope(success=True, results=cards, summary='')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'anything'})

    data = r.json()
    assert data['response'] != ''
    assert '1 product' in data['response']


def test_amazon_response_text_non_empty_when_no_results():
    fake = _mock_envelope(success=False, results=[], summary='', error='')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'anything'})

    data = r.json()
    assert data['response'] != ''
    assert 'No products' in data['response']


def test_amazon_uses_skill_summary_when_present():
    cards = [_FakeCard('D', 90)]
    fake = _mock_envelope(success=True, results=cards, summary='Custom summary from skill.')
    with patch('app.web_ui.routes.amazon_ui_skill.search', return_value=fake):
        r = client.post('/amazon', json={'query': 'anything'})

    assert r.json()['response'] == 'Custom summary from skill.'


def test_amazon_missing_query_returns_422():
    r = client.post('/amazon', json={})
    assert r.status_code == 422
