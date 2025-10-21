from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .kabutan import KabutanProvider
from .models import AnnualRecord, CompanyInfo, QuarterlyRecord
from .yahoo_jp import YahooJapanProvider

LOGGER = logging.getLogger(__name__)


class FinancialDataProvider:
    """Aggregate financial records from Yahoo Japan and Kabutan."""

    def __init__(self) -> None:
        self.yahoo = YahooJapanProvider()
        self.kabutan = KabutanProvider()
        self._info_cache: dict[str, CompanyInfo] = {}

    @staticmethod
    def _merge_annual(*record_sets: Iterable[AnnualRecord]) -> List[AnnualRecord]:
        merged: dict[str, AnnualRecord] = {}
        for records in record_sets:
            for record in records:
                if record.is_forecast:
                    continue
                key = record.end_date.isoformat()
                existing = merged.get(key)
                if existing and existing.source == "yahoo_jp" and record.source != "yahoo_jp":
                    continue
                merged[key] = record
        return sorted(merged.values(), key=lambda r: r.end_date, reverse=True)

    @staticmethod
    def _merge_quarterly(*record_sets: Iterable[QuarterlyRecord]) -> List[QuarterlyRecord]:
        merged: dict[str, QuarterlyRecord] = {}
        for records in record_sets:
            for record in records:
                key = record.end_date.isoformat()
                existing = merged.get(key)
                if existing and existing.source == "yahoo_jp" and record.source != "yahoo_jp":
                    continue
                merged[key] = record
        return sorted(merged.values(), key=lambda r: r.end_date, reverse=True)

    def get_annual(self, symbol: str) -> List[AnnualRecord]:
        try:
            kabutan_records = self.kabutan.get_annual(symbol)
        except Exception as exc:
            LOGGER.debug("Kabutan annual fetch failed for %s: %s", symbol, exc)
            kabutan_records = []
        try:
            yahoo_records = self.yahoo.get_annual(symbol)
        except Exception as exc:
            LOGGER.debug("Yahoo annual fetch failed for %s: %s", symbol, exc)
            yahoo_records = []
        return self._merge_annual(kabutan_records, yahoo_records)

    def get_quarterly(self, symbol: str) -> List[QuarterlyRecord]:
        try:
            kabutan_records = self.kabutan.get_quarterly(symbol)
        except Exception as exc:
            LOGGER.debug("Kabutan quarterly fetch failed for %s: %s", symbol, exc)
            kabutan_records = []
        try:
            yahoo_records = self.yahoo.get_quarterly(symbol)
        except Exception as exc:
            LOGGER.debug("Yahoo quarterly fetch failed for %s: %s", symbol, exc)
            yahoo_records = []
        return self._merge_quarterly(kabutan_records, yahoo_records)

    def get_company_info(self, symbol: str) -> Optional[CompanyInfo]:
        cached = self._info_cache.get(symbol)
        if cached:
            return cached
        try:
            info = self.kabutan.get_company_info(symbol)
        except Exception as exc:
            LOGGER.debug("Kabutan company info fetch failed for %s: %s", symbol, exc)
            info = None
        if info:
            self._info_cache[symbol] = info
        return info
