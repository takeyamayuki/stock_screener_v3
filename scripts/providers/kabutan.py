from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .models import AnnualRecord, QuarterlyRecord
from .utils import (
    last_day_of_month,
    parse_quarter_range,
    parse_unit_from_info,
    parse_year_month,
    to_number,
    unit_multiplier,
)


LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36"
)


class KabutanProvider:
    """Fetch financial tables from kabutan.jp."""

    BASE_URL = "https://kabutan.jp/stock/finance"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def _fetch_dom(self, symbol: str) -> BeautifulSoup:
        code = symbol.split(".")[0]
        resp = self.session.get(self.BASE_URL, params={"code": code}, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _find_table(self, soup: BeautifulSoup, heading: str, min_rows: int, max_rows: int) -> Optional[BeautifulSoup]:
        for node in soup.select("h2, h3"):
            if node.get_text(strip=True) != heading:
                continue
            table = node.find_next("table")
            if not table:
                continue
            rows = len(table.find_all("tr"))
            if min_rows <= rows <= max_rows:
                return table
        return None

    def _extract_unit_info(self, table: BeautifulSoup) -> str:
        info_block = table.find_next("ul", class_="info")
        if not info_block:
            return "百万円"
        info_text = " ".join(li.get_text(strip=True) for li in info_block.find_all("li"))
        return parse_unit_from_info(info_text, default="百万円")

    def get_annual(self, symbol: str) -> List[AnnualRecord]:
        soup = self._fetch_dom(symbol)
        table = self._find_table(soup, heading="業績推移", min_rows=6, max_rows=10)
        if not table:
            LOGGER.warning("Kabutan annual table missing for %s", symbol)
            return []
        unit_label = self._extract_unit_info(table)
        multiplier = unit_multiplier(unit_label)

        records: List[AnnualRecord] = []
        for row in table.select("tbody tr"):
            cells = [cell for cell in row.find_all(["th", "td"])]
            if not cells:
                continue
            text_cells = [cell.get_text(strip=True) for cell in cells]
            label = text_cells[0]
            if not label or "前期比" in label or "前年同期比" in label:
                continue

            is_forecast = "予" in label
            scope = None
            span = cells[0].find("span")
            if span:
                scope = span.get_text(strip=True)
                label = label.replace(scope, "", 1).strip()
            label = label.replace("予", "").strip()

            ym = parse_year_month(label)
            if not ym:
                LOGGER.debug("Skipping annual row with unparsable label %s", label)
                continue
            year, month = ym
            end_date = last_day_of_month(year, month)

            revenue = to_number(text_cells[1], multiplier)
            ordinary = to_number(text_cells[3], multiplier)
            accounting_standard = None
            if scope == "I":
                accounting_standard = "IFRS"
            record = AnnualRecord(
                period_label=label,
                end_date=end_date,
                revenue=revenue,
                ordinary_income=ordinary,
                scope=scope,
                accounting_standard=accounting_standard,
                unit="JPY",
                source="kabutan",
                is_forecast=is_forecast,
            )
            if not is_forecast:
                records.append(record)
        return records

    def get_quarterly(self, symbol: str) -> List[QuarterlyRecord]:
        soup = self._fetch_dom(symbol)
        table = self._find_table(soup, heading="業績推移", min_rows=11, max_rows=20)
        if not table:
            LOGGER.warning("Kabutan quarterly table missing for %s", symbol)
            return []
        unit_label = self._extract_unit_info(table)
        multiplier = unit_multiplier(unit_label)

        records: List[QuarterlyRecord] = []
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            if not label or "前年同期比" in label:
                continue
            scope = None
            span = cells[0].find("span")
            if span:
                scope = span.get_text(strip=True)
                label = label.replace(scope, "", 1).strip()
            label = label.replace("予", "").strip()

            ym = parse_quarter_range(label)
            if not ym:
                LOGGER.debug("Skipping quarterly row with unparsable label %s", label)
                continue
            year, end_month = ym
            end_date = last_day_of_month(year, end_month)

            revenue = to_number(cells[1].get_text(strip=True), multiplier)
            ordinary = to_number(cells[3].get_text(strip=True), multiplier)
            accounting_standard = None
            if scope == "I":
                accounting_standard = "IFRS"
            records.append(
                QuarterlyRecord(
                    period_label=label,
                    end_date=end_date,
                    revenue=revenue,
                    ordinary_income=ordinary,
                    scope=scope,
                    accounting_standard=accounting_standard,
                    unit="JPY",
                    source="kabutan",
                )
            )
        return records

