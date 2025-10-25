from pathlib import Path

import pytest

import scripts.fetch_symbols_ppx as fetch


class DummyResponse:
    def __init__(self, text: str = "", status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return {
            "choices": [
                {"message": {"content": '{"codes": ["1234", "5678"]}'}}
            ]
        }


def test_perplexity_fetch_json_success(monkeypatch):
    monkeypatch.setattr(fetch, "PPX_KEY", "dummy")
    monkeypatch.setattr(fetch.requests, "post", lambda *_, **__: DummyResponse())
    data = fetch.perplexity_fetch_json("prompt", "sonar-pro")
    assert data["codes"] == ["1234", "5678"]


def test_perplexity_fetch_json_handles_invalid(monkeypatch):
    class BadResponse(DummyResponse):
        def json(self):
            return {"choices": [{"message": {"content": "invalid"}}]}

    monkeypatch.setattr(fetch.requests, "post", lambda *_, **__: BadResponse())
    assert fetch.perplexity_fetch_json("prompt", "sonar") == {}


def test_perplexity_fetch_json_handles_exception(monkeypatch):
    class BrokenResponse(DummyResponse):
        def json(self):
            return {"choices": [{"message": {"content": '{"codes":[}'}}]}

    monkeypatch.setattr(fetch.requests, "post", lambda *_, **__: BrokenResponse())
    assert fetch.perplexity_fetch_json("prompt", "sonar") == {}


def test_try_perplexity_codes_for_market(monkeypatch):
    calls = []

    def fake_fetch(prompt, model):
        calls.append((prompt, model))
        if len(calls) == 1:
            raise RuntimeError("boom")
        return {"codes": ["1234", "abcd", "5678"]}

    monkeypatch.setattr(fetch, "PPX_KEY", "key")
    monkeypatch.setattr(fetch, "perplexity_fetch_json", fake_fetch)
    codes = fetch.try_perplexity_codes_for_market("プライム")
    assert codes == ["1234", "5678"]


def test_try_perplexity_codes_without_key(monkeypatch):
    monkeypatch.setattr(fetch, "PPX_KEY", "")
    assert fetch.try_perplexity_codes_for_market("プライム") == []


def test_try_perplexity_codes_returns_empty_when_no_matches(monkeypatch):
    monkeypatch.setattr(fetch, "PPX_KEY", "key")

    def fake_fetch(prompt, model):
        return {"codes": []}

    monkeypatch.setattr(fetch, "perplexity_fetch_json", fake_fetch)
    assert fetch.try_perplexity_codes_for_market("プライム") == []


def test_iter_kabutan_candidates(monkeypatch):
    html_with_codes = '''<table class="stock_table"><tbody>
        <tr><td>1234</td><td>東Ｐ</td></tr>
        <tr><td>ABCD</td><td>東Ｐ</td></tr>
    </tbody></table>'''
    responses = [DummyResponse(html_with_codes), DummyResponse(status=404)]

    def fake_get(*_, **__):
        return responses.pop(0)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    result = list(fetch.iter_kabutan_candidates(max_pages=2))
    assert result == [("1234", "プライム")]


def test_iter_kabutan_candidates_handles_error(monkeypatch):
    monkeypatch.setattr(fetch.requests, "get", lambda *_, **__: (_ for _ in ()).throw(RuntimeError("fail")))
    assert list(fetch.iter_kabutan_candidates(max_pages=1)) == []


def test_iter_kabutan_candidates_handles_empty_rows(monkeypatch):
    html = '<table class="stock_table"><tbody><tr></tr></tbody></table>'
    responses = [DummyResponse(html), DummyResponse(status=404)]
    monkeypatch.setattr(fetch.requests, "get", lambda *_, **__: responses.pop(0))
    assert list(fetch.iter_kabutan_candidates(max_pages=2)) == []


def test_iter_kabutan_candidates_breaks_when_no_rows(monkeypatch):
    html = '<table class="stock_table"><tbody></tbody></table>'
    monkeypatch.setattr(fetch.requests, "get", lambda *_, **__: DummyResponse(html))
    assert list(fetch.iter_kabutan_candidates(max_pages=1)) == []


def test_lookup_market_and_cache(monkeypatch):
    fetch.INFO_CACHE.clear()

    class InfoStub:
        def __init__(self):
            self.calls = 0

        def get_company_info(self, symbol):
            self.calls += 1
            return type("Info", (), {"market": "プライム"})()

    stub = InfoStub()
    monkeypatch.setattr(fetch, "KABUTAN_PROVIDER", stub)

    assert fetch.lookup_market("1234") == "プライム"
    assert fetch.lookup_market("1234") == "プライム"
    assert stub.calls == 1


def test_lookup_market_handles_exception(monkeypatch):
    fetch.INFO_CACHE.clear()

    class Failing:
        def get_company_info(self, symbol):
            raise RuntimeError("error")

    monkeypatch.setattr(fetch, "KABUTAN_PROVIDER", Failing())
    assert fetch.lookup_market("9999") is None


def test_add_codes_and_ensure_minimum(monkeypatch):
    collected = {market: [] for market in fetch.TARGET_MARKETS}
    fetch.add_codes(collected, [("1234", "プライム"), ("1234", "プライム")])
    assert collected["プライム"] == ["1234"]

    # Ignore unknown market and respect bucket limit
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 1)
    fetch.add_codes(collected, [("9999", "UNKNOWN"), ("8888", "プライム")])
    assert collected["プライム"] == ["1234"]

    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム",))
    monkeypatch.setattr(fetch, "try_perplexity_codes_for_market", lambda market: ["5678"])
    monkeypatch.setattr(fetch, "lookup_market", lambda code: "プライム")
    collected = {"プライム": []}
    fetch.ensure_minimum_codes(collected)
    assert collected["プライム"] == ["5678"]

    collected_full = {"プライム": ["1234"]}
    fetch.ensure_minimum_codes(collected_full)
    assert collected_full["プライム"] == ["1234"]

    monkeypatch.setattr(fetch, "try_perplexity_codes_for_market", lambda market: [])
    fetch.ensure_minimum_codes(collected_full)
    empty_collected = {"プライム": []}
    fetch.ensure_minimum_codes(empty_collected)
    assert empty_collected["プライム"] == []


def test_main_writes_symbols(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム", "スタンダード"))
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 1)
    monkeypatch.setattr(fetch, "MAX_SYMBOLS", 2)
    temp_file = tmp_path / "symbols.txt"
    monkeypatch.setattr(fetch, "SYMBOLS_PATH", temp_file)

    monkeypatch.setattr(fetch, "iter_kabutan_candidates", lambda max_pages=60: [("1234", "プライム")])
    monkeypatch.setattr(fetch, "ensure_minimum_codes", lambda collected: fetch.add_codes(collected, [("5678", "スタンダード")]))

    fetch.main()

    assert temp_file.read_text(encoding="utf-8").splitlines() == ["1234.T", "5678.T"]


def test_main_logs_missing_counts(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム", "スタンダード"))
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 2)
    monkeypatch.setattr(fetch, "MAX_SYMBOLS", 10)
    monkeypatch.setattr(fetch, "SYMBOLS_PATH", tmp_path / "symbols.txt")
    monkeypatch.setattr(fetch, "iter_kabutan_candidates", lambda max_pages=60: [("1234", "プライム")])
    monkeypatch.setattr(fetch, "ensure_minimum_codes", lambda collected: None)
    monkeypatch.setattr(fetch, "log", lambda msg: logs.append(msg))

    fetch.main()

    assert any("プライム は 1 件しか" in msg for msg in logs)


def test_main_outputs_final_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム",))
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 1)
    monkeypatch.setattr(fetch, "MAX_SYMBOLS", 1)
    monkeypatch.setattr(fetch, "SYMBOLS_PATH", tmp_path / "symbols.txt")
    monkeypatch.setattr(fetch, "iter_kabutan_candidates", lambda max_pages=60: [("1111", "プライム")])
    monkeypatch.setattr(fetch, "ensure_minimum_codes", lambda collected: None)

    fetch.main()

    captured = capsys.readouterr().err
    assert "symbols written" in captured
