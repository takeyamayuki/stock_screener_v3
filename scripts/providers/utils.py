from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from typing import Optional


UNIT_MULTIPLIERS = {
    "円": 1,
    "千円": 1_000,
    "百万円": 1_000_000,
    "億円": 100_000_000,
    "兆円": 1_000_000_000_000,
}


def parse_unit_from_info(info_text: str, default: str = "百万円") -> str:
    """Extract unit label from Kabutan info text."""

    if not info_text:
        return default
    match = re.search(r"：[^「]*「([^」]+)」", info_text)
    if match:
        return match.group(1)
    return default


def unit_multiplier(unit_label: str) -> int:
    """Return multiplier for numeric values based on unit label."""

    return UNIT_MULTIPLIERS.get(unit_label, 1)


def to_number(value: str, multiplier: int) -> Optional[float]:
    """Convert Kabutan numeric string to float in yen."""

    value = value.strip()
    if not value or value in {"-", "—", "－", "", "- -"}:
        return None
    value = value.replace(",", "")
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def parse_year_month(label: str) -> Optional[tuple[int, int]]:
    """Return (year, month) for labels like '2024.03' or '23.07'."""

    match = re.search(r"(\d{2,4})\.(\d{2})", label)
    if not match:
        return None
    year = int(match.group(1))
    if year < 100:
        year += 2000 if year < 70 else 1900
    month = int(match.group(2))
    return year, month


def parse_quarter_range(label: str) -> Optional[tuple[int, int]]:
    """Return (year, end_month) for labels like '23.07-09'."""

    match = re.search(r"(\d{2,4})\.(\d{2})-(\d{2})", label)
    if not match:
        return None
    year = int(match.group(1))
    if year < 100:
        year += 2000 if year < 70 else 1900
    end_month = int(match.group(3))
    return year, end_month


def last_day_of_month(year: int, month: int) -> date:
    """Return last calendar day of given month."""

    return date(year, month, monthrange(year, month)[1])

