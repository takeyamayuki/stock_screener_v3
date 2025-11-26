from __future__ import annotations

import os
import time
from datetime import date
from typing import List, Optional

import requests

from .models import AnnualRecord, CompanyInfo, QuarterlyRecord

ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY")
ALPHAVANTAGE_US_THROTTLE_SECONDS = float(os.environ.get("ALPHAVANTAGE_US_THROTTLE_SECONDS", "13"))


def _parse_date(value: str) -> date:
    parts = value.split("-")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


class AlphaVantageUS:
    def __init__(self) -> None:
        if not ALPHAVANTAGE_KEY:
            raise RuntimeError("ALPHAVANTAGE_KEY is required for US screener")

    def _get_json(self, params: dict) -> dict:
        params = {**params, "apikey": ALPHAVANTAGE_KEY}
        resp = requests.get("https://www.alphavantage.co/query", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(ALPHAVANTAGE_US_THROTTLE_SECONDS)
        return data

    def get_annual(self, symbol: str) -> List[AnnualRecord]:
        data = self._get_json({"function": "INCOME_STATEMENT", "symbol": symbol})
        records: List[AnnualRecord] = []
        for item in data.get("annualReports", []):
            end = item.get("fiscalDateEnding")
            if not end:
                continue
            records.append(
                AnnualRecord(
                    period_label=end[:4],
                    end_date=_parse_date(end),
                    ordinary_income=_safe_float(item.get("operatingIncome")),
                    revenue=_safe_float(item.get("totalRevenue")),
                    ordinary_income_yoy=None,
                    revenue_yoy=None,
                    currency=item.get("reportedCurrency"),
                    source="alpha_vantage",
                )
            )
        return records

    def get_quarterly(self, symbol: str) -> List[QuarterlyRecord]:
        data = self._get_json({"function": "INCOME_STATEMENT", "symbol": symbol})
        records: List[QuarterlyRecord] = []
        for item in data.get("quarterlyReports", []):
            end = item.get("fiscalDateEnding")
            if not end:
                continue
            label = f"{end[:4]}Q{((int(end[5:7]) - 1) // 3) + 1}"
            records.append(
                QuarterlyRecord(
                    period_label=label,
                    end_date=_parse_date(end),
                    ordinary_income=_safe_float(item.get("operatingIncome")),
                    revenue=_safe_float(item.get("totalRevenue")),
                    ordinary_income_yoy=None,
                    revenue_yoy=None,
                    currency=item.get("reportedCurrency"),
                    source="alpha_vantage",
                )
            )
        return records

    def get_company_info(self, symbol: str) -> Optional[CompanyInfo]:
        data = self._get_json({"function": "OVERVIEW", "symbol": symbol})
        name = data.get("Name")
        if not name:
            return None
        per = _safe_float(data.get("PERatio"))
        market = data.get("Exchange") or ""
        return CompanyInfo(
            symbol=symbol,
            name=name,
            market=market,
            market_code=market,
            source="alpha_vantage",
            per=per,
        )
