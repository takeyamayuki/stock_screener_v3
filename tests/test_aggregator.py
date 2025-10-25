from datetime import date

import pytest

from scripts.providers.aggregator import FinancialDataProvider
from scripts.providers.models import AnnualRecord, CompanyInfo, QuarterlyRecord


def make_annual(end_date, value, source, forecast=False):
    return AnnualRecord(
        period_label="2024",
        end_date=end_date,
        revenue=100,
        ordinary_income=value,
        scope=None,
        accounting_standard=None,
        unit="JPY",
        source=source,
        is_forecast=forecast,
    )


def make_quarter(end_date, value, source):
    return QuarterlyRecord(
        period_label="2024Q4",
        end_date=end_date,
        revenue=50,
        ordinary_income=value,
        scope=None,
        accounting_standard=None,
        unit="JPY",
        source=source,
    )


def test_merge_annual_prefers_latest_non_forecast():
    records = FinancialDataProvider._merge_annual(
        [make_annual(date(2024, 4, 30), 10, "kabutan"), make_annual(date(2025, 4, 30), 20, "kabutan", forecast=True)],
        [make_annual(date(2024, 4, 30), 15, "yahoo_jp")],
    )
    assert len(records) == 1
    assert records[0].ordinary_income == 15


def test_merge_quarterly_retains_yahoo_priority():
    records = FinancialDataProvider._merge_quarterly(
        [make_quarter(date(2024, 12, 31), 8, "kabutan")],
        [make_quarter(date(2024, 12, 31), 9, "yahoo_jp")],
    )
    assert len(records) == 1
    assert records[0].ordinary_income == 9


def test_merge_annual_skip_when_yahoo_already_selected():
    records = FinancialDataProvider._merge_annual(
        [make_annual(date(2023, 3, 31), 8, "yahoo_jp")],
        [make_annual(date(2023, 3, 31), 12, "kabutan")],
    )
    assert records[0].ordinary_income == 8


class _StubProvider:
    def __init__(self, annual=None, quarterly=None, info=None, raise_on=False):
        self.annual = annual or []
        self.quarterly = quarterly or []
        self.info = info
        self.raise_on = raise_on
        self.calls = 0

    def get_annual(self, symbol):
        if self.raise_on:
            raise RuntimeError("kabutan error")
        self.calls += 1
        return self.annual

    def get_quarterly(self, symbol):
        if self.raise_on:
            raise RuntimeError("kabutan error")
        self.calls += 1
        return self.quarterly

    def get_company_info(self, symbol):
        if self.raise_on and self.calls < 1:
            raise RuntimeError("kabutan error")
        self.calls += 1
        return self.info


def test_financial_data_provider_fetches_with_fallback(monkeypatch):
    yahoo_stub = _StubProvider(annual=[make_annual(date(2024, 4, 30), 11, "yahoo_jp")],
                               quarterly=[make_quarter(date(2024, 12, 31), 6, "yahoo_jp")])
    kabutan_stub = _StubProvider(raise_on=True)
    provider = FinancialDataProvider()
    provider.yahoo = yahoo_stub
    provider.kabutan = kabutan_stub

    annual = provider.get_annual("5032.T")
    quarterly = provider.get_quarterly("5032.T")

    assert len(annual) == 1 and annual[0].ordinary_income == 11
    assert len(quarterly) == 1 and quarterly[0].ordinary_income == 6


def test_financial_data_provider_handles_all_failures(monkeypatch):
    stub = _StubProvider(raise_on=True)
    provider = FinancialDataProvider()
    provider.yahoo = stub
    provider.kabutan = stub

    assert provider.get_annual("5032.T") == []
    assert provider.get_quarterly("5032.T") == []


def test_get_company_info_caches_result(monkeypatch):
    info = CompanyInfo("5032.T", "テスト", "プライム", "東証Ｐ", "kabutan")
    kabutan_stub = _StubProvider(info=info)
    provider = FinancialDataProvider()
    provider.kabutan = kabutan_stub

    first = provider.get_company_info("5032.T")
    second = provider.get_company_info("5032.T")

    assert first is second
    assert kabutan_stub.calls == 1


def test_get_company_info_handles_exception(monkeypatch):
    kabutan_stub = _StubProvider(raise_on=True)
    provider = FinancialDataProvider()
    provider.kabutan = kabutan_stub

    assert provider.get_company_info("5032.T") is None
