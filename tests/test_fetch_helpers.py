from dataclasses import dataclass

from scripts import screener


@dataclass
class _DummyRecord:
    period_label: str
    end_date: str
    revenue: float
    ordinary_income: float


class _FlakyProvider:
    def __init__(self):
        self.calls = 0

    def get_annual(self, symbol: str):
        self.calls += 1
        if self.calls < 2:
            return []
        return [_DummyRecord("2024", "2024-02-29", 100.0, 25.0)]

    def get_quarterly(self, symbol: str):
        if self.calls < 2:
            return []
        return [_DummyRecord("2024Q4", "2024-02-29", 25.0, 6.0)]

    def get_company_info(self, symbol: str):
        return None


def test_fetch_financials_retries_until_success(monkeypatch):
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_DELAY", 0)
    provider = _FlakyProvider()
    annual, quarterly = screener.fetch_financials(provider, "TEST.T")
    assert provider.calls == 2
    assert len(annual) == 1
    assert len(quarterly) == 1


class _FlakyInfoProvider(_FlakyProvider):
    def __init__(self):
        super().__init__()
        self.info_calls = 0

    def get_company_info(self, symbol: str):
        self.info_calls += 1
        if self.info_calls < 3:
            return None
        return screener.CompanyInfo(symbol, "テスト社", "プライム", "東証Ｐ", "stub")


def test_fetch_company_info_retries(monkeypatch):
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(screener, "FINANCIAL_RETRY_DELAY", 0)
    provider = _FlakyInfoProvider()
    info = screener.fetch_company_info(provider, "TEST.T")
    assert info is not None
    assert provider.info_calls == 3
