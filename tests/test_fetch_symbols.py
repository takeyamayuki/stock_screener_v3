import scripts.fetch_symbols_ppx as fetch


class DummyResponse:
    def __init__(self, text: str = "", status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


def make_html_row(code: str, market_abbr: str = "東Ｐ") -> str:
    return f"<tr><td>{code}</td><td>{market_abbr}</td></tr>"


def test_iter_kabutan_candidates(monkeypatch):
    html_with_codes = '''<table class="stock_table"><tbody>
        {row1}
        {row2}
        {row3}
    </tbody></table>'''.format(
        row1=make_html_row("1234", "東Ｐ"),
        row2=make_html_row("ABCD", "東Ｐ"),
        row3=make_html_row("247a", "名Ｎ"),
    )
    responses = [DummyResponse(html_with_codes), DummyResponse(status=404)]
    params_seen = []

    def fake_get(url, params=None, **kwargs):
        params_seen.append(params)
        return responses.pop(0)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    result = list(fetch.iter_kabutan_candidates("プライム", max_pages=2))
    assert result == [("1234", "プライム"), ("247A", "プライム")]
    assert params_seen[0] == {"market": "1"}


def test_iter_kabutan_candidates_handles_error(monkeypatch):
    monkeypatch.setattr(
        fetch.requests,
        "get",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("fail")),
    )
    assert list(fetch.iter_kabutan_candidates("プライム", max_pages=1)) == []


def test_iter_kabutan_candidates_handles_empty_rows(monkeypatch):
    html = '<table class="stock_table"><tbody><tr></tr></tbody></table>'
    responses = [DummyResponse(html), DummyResponse(status=404)]
    monkeypatch.setattr(
        fetch.requests,
        "get",
        lambda *_, **__: responses.pop(0),
    )
    assert list(fetch.iter_kabutan_candidates("プライム", max_pages=2)) == []


def test_iter_kabutan_candidates_breaks_when_no_rows(monkeypatch):
    html = '<table class="stock_table"><tbody></tbody></table>'
    monkeypatch.setattr(fetch.requests, "get", lambda *_, **__: DummyResponse(html))
    assert list(fetch.iter_kabutan_candidates("プライム", max_pages=1)) == []


def test_add_codes_respects_limits(monkeypatch):
    collected = {market: [] for market in fetch.TARGET_MARKETS}
    fetch.add_codes(collected, [("1234", "プライム"), ("1234", "プライム")])
    assert collected["プライム"] == ["1234"]

    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 1)
    fetch.add_codes(collected, [("9999", "UNKNOWN"), ("8888", "プライム")])
    assert collected["プライム"] == ["1234"]


def test_main_writes_symbols(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム", "スタンダード"))
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 1)
    monkeypatch.setattr(fetch, "MAX_SYMBOLS", 2)
    temp_file = tmp_path / "symbols.txt"
    monkeypatch.setattr(fetch, "SYMBOLS_PATH", temp_file)

    def fake_iter(market, max_pages=60):
        return [("1234", market)] if market == "プライム" else [("5678", market)]

    monkeypatch.setattr(fetch, "iter_kabutan_candidates", fake_iter)

    fetch.main()

    assert temp_file.read_text(encoding="utf-8").splitlines() == ["1234.T", "5678.T"]


def test_main_logs_missing_counts(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(fetch, "TARGET_MARKETS", ("プライム", "スタンダード"))
    monkeypatch.setattr(fetch, "TARGET_PER_MARKET", 2)
    monkeypatch.setattr(fetch, "MAX_SYMBOLS", 10)
    monkeypatch.setattr(fetch, "SYMBOLS_PATH", tmp_path / "symbols.txt")

    def fake_iter(market, max_pages=60):
        return [("1234", "プライム")] if market == "プライム" else []

    monkeypatch.setattr(fetch, "iter_kabutan_candidates", fake_iter)
    monkeypatch.setattr(fetch, "log", lambda msg: logs.append(msg))

    fetch.main()

    assert any("プライム は 1 件しか" in msg for msg in logs)
