from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scripts.providers.kabutan import KabutanProvider


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
