"""Financial data provider package."""

from .aggregator import FinancialDataProvider
from .models import AnnualRecord, QuarterlyRecord

__all__ = [
    "FinancialDataProvider",
    "AnnualRecord",
    "QuarterlyRecord",
]

