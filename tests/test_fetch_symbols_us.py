import scripts.fetch_symbols_us as fetch_us


def test_fetch_symbols_us_returns_list(monkeypatch):
    html = """
    <table>
      <tr><th>ﾃｨｯｶｰ△▽</th></tr>
      <tr><td>AAPL</td><td>Apple</td></tr>
      <tr><td>MSFT</td><td>Microsoft</td></tr>
    </table>
    """
    monkeypatch.setattr(
        fetch_us.requests,
        "get",
        lambda *_, **__: type("Resp", (), {"text": html, "raise_for_status": lambda self=None: None})(),
    )

    symbols = fetch_us.fetch_symbols()
    assert symbols == ["AAPL", "MSFT"]
