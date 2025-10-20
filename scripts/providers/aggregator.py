from __future__ import annotations

from typing import Iterable, List, Optional

from .kabutan import KabutanProvider
from .models import AnnualRecord, QuarterlyRecord
from .yahoo_jp import YahooJapanProvider


class FinancialDataProvider:
    """Aggregate financial records from Yahoo Japan and Kabutan."""

    def __init__(self) -> None:
        self.yahoo = YahooJapanProvider()
        self.kabutan = KabutanProvider()

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
        kabutan_records = self.kabutan.get_annual(symbol)
        yahoo_records = self.yahoo.get_annual(symbol)
        return self._merge_annual(kabutan_records, yahoo_records)

    def get_quarterly(self, symbol: str) -> List[QuarterlyRecord]:
        kabutan_records = self.kabutan.get_quarterly(symbol)
        yahoo_records = self.yahoo.get_quarterly(symbol)
        return self._merge_quarterly(kabutan_records, yahoo_records)
