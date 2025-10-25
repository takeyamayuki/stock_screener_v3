from pathlib import Path

import pytest

from scripts.providers.yahoo_jp import YahooJapanProvider


class LocalYahoo(YahooJapanProvider):
    def __init__(self):
        super().__init__()

    def _fetch_html(self, symbol: str, params=None):
        if params:
            path = Path("tests/fixtures/html/yahoo_5032_quarter.html")
        else:
            path = Path("tests/fixtures/html/yahoo_5032_performance.html")
        return path.read_text(encoding="utf-8")


def test_yahoo_get_annual_records():
    provider = LocalYahoo()
    records = provider.get_annual("5032.T")
    assert [r.period_label for r in records] == ["2025Q4", "2024"]
    assert records[0].revenue == pytest.approx(42876000000.0)
    assert records[0].source == "yahoo_jp"


def test_yahoo_get_quarterly_records():
    provider = LocalYahoo()
    records = provider.get_quarterly("5032.T")
    assert [r.period_label for r in records] == ["2025Q2", "2025Q1"]
    assert records[0].revenue == pytest.approx(15768000000.0)


def test_yahoo_fetch_html_handles_errors():
    provider = YahooJapanProvider()

    class Response:
        def __init__(self, status=500):
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400 and self.status_code < 500:
                raise RuntimeError("client error")

        @property
        def text(self):
            return ""

    provider.session.get = lambda *_, **__: Response(500)  # type: ignore[attr-defined]
    assert provider._fetch_html("5032.T") is None

    import requests

    provider.session.get = lambda *_, **__: (_ for _ in ()).throw(requests.RequestException("fail"))  # type: ignore[attr-defined]
    assert provider._fetch_html("5032.T") is None
