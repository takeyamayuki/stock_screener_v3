from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scripts.providers.kabutan import KabutanProvider


class DummyResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("error")


@pytest.fixture(scope="module")
def finance_html():
    return Path("tests/fixtures/html/kabutan_5032_finance.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def company_html():
    return Path("tests/fixtures/html/kabutan_5032_company.html").read_text(encoding="utf-8")


def test_kabutan_get_financials_from_fixture(monkeypatch, finance_html):
    soup = BeautifulSoup(finance_html, "lxml")

    def fake_fetch_dom(self, symbol: str):
        return soup

    monkeypatch.setattr(KabutanProvider, "_fetch_dom", fake_fetch_dom)

    provider = KabutanProvider()
    annual = provider.get_annual("5032.T")
    quarterly = provider.get_quarterly("5032.T")

    assert len(annual) >= 4
    assert len(quarterly) >= 8
    assert annual[-1].period_label == "2025.04"
    assert annual[-1].ordinary_income == pytest.approx(16214000000.0)
    assert quarterly[-1].period_label == "25.05-07"
    assert quarterly[-1].revenue == pytest.approx(15768000000.0)


def test_kabutan_get_company_info(monkeypatch, company_html):
    soup = BeautifulSoup(company_html, "lxml")

    def fake_fetch_company_dom(self, symbol: str):
        return soup

    monkeypatch.setattr(KabutanProvider, "_fetch_company_dom", fake_fetch_company_dom)

    provider = KabutanProvider()
    info = provider.get_company_info("5032.T")

    assert info is not None
    assert info.name == "ＡＮＹＣＯＬＯＲ"
    assert info.market == "プライム"
    assert info.market_label == "東証Ｐ"


def test_fetch_dom_uses_session(monkeypatch):
    provider = KabutanProvider()

    def fake_get(url, params=None, timeout=30):
        assert params == {"code": "5032"}
        return DummyResponse("<html></html>")

    provider.session.get = fake_get  # type: ignore[attr-defined]
    soup = provider._fetch_dom("5032.T")
    assert soup is not None


def test_fetch_company_dom(monkeypatch):
    provider = KabutanProvider()

    def fake_get(url, timeout=30):
        assert url.endswith("?code=5032")
        return DummyResponse("<html></html>")

    provider.session.get = fake_get  # type: ignore[attr-defined]
    soup = provider._fetch_company_dom("5032.T")
    assert soup is not None


def test_get_annual_handles_missing_table(monkeypatch):
    monkeypatch.setattr(KabutanProvider, "_fetch_dom", lambda self, symbol: BeautifulSoup("<html></html>", "lxml"))
    provider = KabutanProvider()
    assert provider.get_annual("5032.T") == []


def test_get_annual_parses_ifrs(monkeypatch):
    html = '''<table><tbody>
        <tr><th><span class="kubun1">I</span>2024.03</th><td>1,000</td><td>忽略</td><td>500</td></tr>
        <tr><th>dummy</th><td>0</td><td>0</td><td>0</td></tr>
        <tr><th>dummy</th><td>0</td><td>0</td><td>0</td></tr>
        <tr><th>dummy</th><td>0</td><td>0</td><td>0</td></tr>
        <tr><th>dummy</th><td>0</td><td>0</td><td>0</td></tr>
        <tr><th>dummy</th><td>0</td><td>0</td><td>0</td></tr>
    </tbody></table><ul class="info"><li>単位：百万円</li></ul>'''
    monkeypatch.setattr(KabutanProvider, "_fetch_dom", lambda self, symbol: BeautifulSoup("<html></html>", "lxml"))
    monkeypatch.setattr(KabutanProvider, "_find_table", lambda self, soup, heading, min_rows, max_rows: BeautifulSoup(html, "lxml").find("table"))
    provider = KabutanProvider()
    records = provider.get_annual("5032.T")
    assert records[0].accounting_standard == "IFRS"


def test_get_quarterly_parses_rows(monkeypatch):
    html = '''<table><tbody>
        <tr><td>2024.01-03</td><td>1,000</td><td>無視</td><td>300</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
        <tr><td>dummy</td><td>0</td><td>0</td><td>0</td></tr>
    </tbody></table><ul class="info"><li>単位：百万円</li></ul>'''
    monkeypatch.setattr(KabutanProvider, "_fetch_dom", lambda self, symbol: BeautifulSoup("<html></html>", "lxml"))
    monkeypatch.setattr(KabutanProvider, "_find_table", lambda self, soup, heading, min_rows, max_rows: BeautifulSoup(html, "lxml").find("table"))
    provider = KabutanProvider()
    records = provider.get_quarterly("5032.T")
    assert len(records) == 1
