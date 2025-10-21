from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class AnnualRecord:
    """Container for annual financial metrics."""

    period_label: str
    end_date: date
    revenue: Optional[float]
    ordinary_income: Optional[float]
    scope: Optional[str]
    accounting_standard: Optional[str]
    unit: str
    source: str
    is_forecast: bool = False


@dataclass
class QuarterlyRecord:
    """Container for quarterly financial metrics."""

    period_label: str
    end_date: date
    revenue: Optional[float]
    ordinary_income: Optional[float]
    scope: Optional[str]
    accounting_standard: Optional[str]
    unit: str
    source: str


@dataclass
class CompanyInfo:
    """Basic company metadata."""

    symbol: str
    name: Optional[str]
    market: Optional[str]
    market_label: Optional[str]
    source: str
