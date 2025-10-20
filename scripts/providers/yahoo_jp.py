from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import List, Optional

import requests

from .models import AnnualRecord, QuarterlyRecord


LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36"
)


class YahooJapanProvider:
    """Fetch financial metrics from Yahoo!ファイナンス（日本）."""

    BASE_URL = "https://finance.yahoo.co.jp/quote/{symbol}/performance"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def _fetch_html(self, symbol: str, params: Optional[dict] = None) -> str:
        url = self.BASE_URL.format(symbol=symbol)
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _extract_performance(self, html: str) -> Optional[list]:
        idx = html.find('"performance":{"performance"')
        if idx == -1:
            return None
        end = html.find('},"stockRanking"', idx)
        if end == -1:
            return None
        block = html[idx:end + 1]
        json_text = "{" + block + "}"
        json_text = json_text.replace("$undefined", "null")
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            LOGGER.debug("Failed to decode Yahoo performance block: %s", exc)
            return None
        performance = data.get("performance", {}).get("performance")
        if not isinstance(performance, list):
            return None
        return performance

    def get_annual(self, symbol: str) -> List[AnnualRecord]:
        html = self._fetch_html(symbol)
        nodes = self._extract_performance(html) or []
        records: List[AnnualRecord] = []
        for node in nodes:
            try:
                end_date = date.fromisoformat(node["endDate"])
            except (KeyError, TypeError, ValueError):
                continue
            revenue = node.get("netSales")
            ordinary = node.get("ordinaryIncome")
            accounting_standard = node.get("accountingStandard")
            fiscal_year = node.get("fiscalYear")
            period_label = f"{fiscal_year}"
            fiscal_quarter = node.get("fiscalQuarter")
            if fiscal_quarter and fiscal_quarter.upper().startswith("Q"):
                period_label = f"{fiscal_year}{fiscal_quarter.upper()}"
            records.append(
                AnnualRecord(
                    period_label=period_label,
                    end_date=end_date,
                    revenue=float(revenue) if revenue is not None else None,
                    ordinary_income=float(ordinary) if ordinary is not None else None,
                    scope=None,
                    accounting_standard=accounting_standard,
                    unit="JPY",
                    source="yahoo_jp",
                    is_forecast=False,
                )
            )
        return records

    def get_quarterly(self, symbol: str) -> List[QuarterlyRecord]:
        html = self._fetch_html(symbol, params={"term": "quarter"})
        nodes = self._extract_performance(html) or []
        records: List[QuarterlyRecord] = []
        for node in nodes:
            try:
                end_date = date.fromisoformat(node["endDate"])
            except (KeyError, TypeError, ValueError):
                continue
            revenue = node.get("netSales")
            ordinary = node.get("ordinaryIncome")
            accounting_standard = node.get("accountingStandard")
            fiscal_year = node.get("fiscalYear")
            quarter = node.get("fiscalQuarter")
            period_label = f"{fiscal_year}{quarter}" if quarter else str(fiscal_year)
            records.append(
                QuarterlyRecord(
                    period_label=period_label,
                    end_date=end_date,
                    revenue=float(revenue) if revenue is not None else None,
                    ordinary_income=float(ordinary) if ordinary is not None else None,
                    scope=None,
                    accounting_standard=accounting_standard,
                    unit="JPY",
                    source="yahoo_jp",
                )
            )
        return records

