"""Hub とフェッチャーの戻り値契約・正規化・非退化判定のテスト。

- フェッチャーは DataFrame を返す。None 等は「データ無し」と区別できないので TypeError。
- 正常応答の0件（空DF）は空DFのまま返り、キャッシュされない。
- 空/全null のDFは退化とみなしキャッシュしない。
"""
from types import SimpleNamespace

import polars as pl
import pytest

from scripts.opendata_hub import OpenDataHub


def _install_fake_freight(hub: OpenDataHub, fetch) -> None:  # noqa: ANN001
    fake = SimpleNamespace(fetch_freight_data=fetch)
    hub._load_module = lambda n, _m=fake, _real=hub._load_module: _m if n == "freight" else _real(n)  # type: ignore[assignment]


def test_none_return_is_type_error_not_silent_empty(hub: OpenDataHub) -> None:
    _install_fake_freight(hub, lambda **kw: None)
    with pytest.raises(TypeError, match="must return a DataFrame"):
        hub.get_freight(tickers="BDRY")


def test_hub_does_not_ask_fetchers_to_write_csv(hub: OpenDataHub) -> None:
    seen: dict[str, object] = {}

    def fetch(**kw: object) -> pl.DataFrame:
        seen.update(kw)
        return pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})

    _install_fake_freight(hub, fetch)
    hub.get_freight(tickers="BDRY")
    assert "output_file" not in seen


def test_empty_result_is_returned_and_not_cached(hub: OpenDataHub) -> None:
    calls = {"n": 0}

    def fetch(**kw: object) -> pl.DataFrame:
        calls["n"] += 1
        return pl.DataFrame()

    _install_fake_freight(hub, fetch)
    assert hub.get_freight(tickers="BDRY").is_empty()
    assert hub.get_freight(tickers="BDRY").is_empty()
    assert calls["n"] == 2  # キャッシュされていない


def test_close_and_adj_close_no_rename_collision(hub: OpenDataHub) -> None:
    """'Close' と 'Adj Close' が両方あっても value 列が重複しない（DuplicateError を防ぐ）。"""
    df = hub._normalize_df(pl.DataFrame({"Date": ["2024-01-01"], "Close": [100], "Adj Close": [99]}))
    assert "date" in df.columns
    assert df.columns.count("value") == 1


def test_validate_df_rejects_all_null(hub: OpenDataHub) -> None:
    bad = pl.DataFrame({"date": [None, None], "value": [None, None]})
    assert hub._is_degenerate(bad) is True


def test_validate_df_accepts_real_data(hub: OpenDataHub) -> None:
    good = pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})
    assert hub._is_degenerate(good) is False


def test_validate_df_empty_is_degenerate(hub: OpenDataHub) -> None:
    assert hub._is_degenerate(pl.DataFrame()) is True
