from datetime import date

import pytest

from scripts.providers import utils


def test_parse_unit_from_info_matches_and_default():
    info = "単位：百万円"
    assert utils.parse_unit_from_info(info) == "百万円"
    assert utils.parse_unit_from_info("", default="千円") == "千円"
    assert utils.parse_unit_from_info("不明", default="円") == "円"


def test_unit_multiplier_known_and_unknown():
    assert utils.unit_multiplier("百万円") == 1_000_000
    assert utils.unit_multiplier("未知") == 1


def test_to_number_parses_and_handles_blanks():
    assert utils.to_number("1,234", 1000) == 1_234_000.0
    assert utils.to_number("-", 1) is None
    assert utils.to_number("", 1) is None
    assert utils.to_number("abc", 1) is None


def test_parse_year_month_and_quarter_range():
    assert utils.parse_year_month("2024.03") == (2024, 3)
    assert utils.parse_year_month("24.03") == (2024, 3)
    assert utils.parse_year_month("abc") is None
    assert utils.parse_quarter_range("24.07-09") == (2024, 9)
    assert utils.parse_quarter_range("invalid") is None


def test_last_day_of_month():
    assert utils.last_day_of_month(2024, 2) == date(2024, 2, 29)
