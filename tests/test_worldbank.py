"""Tests for worldbank_fetcher.py (World Bank wbgapi).

wbgapi には Python 3.12 非互換の SyntaxError があるため、
モジュールレベルでの import を避け、sys.modules に stub を差し込む。
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest

# wbgapi stub: Python 3.12非互換ライブラリをモックで置き換える
_wb_stub = types.ModuleType("wbgapi")
_wb_stub.data = MagicMock()  # type: ignore[attr-defined]
_wb_stub.series = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("wbgapi", _wb_stub)


from worldbank_fetcher import INDICATORS, fetch_worldbank_data, list_aliases

# ── INDICATORS mapping tests ─────────────────────────────────────────────────

def test_indicators_aliases_defined() -> None:
    """主要なエイリアスが定義されている。"""
    for key in ["gdp", "population", "inflation", "gdp_growth"]:
        assert key in INDICATORS
        assert INDICATORS[key].startswith(("NY.", "SP.", "FP.", "SL.", "EN.", "SI."))


def test_indicators_values_are_strings() -> None:
    """全エイリアスの値が文字列であること。"""
    for key, val in INDICATORS.items():
        assert isinstance(val, str), f"{key} value is not a string"


# ── list_aliases smoke test ──────────────────────────────────────────────────

def test_list_aliases_no_crash(capsys: pytest.CaptureFixture) -> None:
    """list_aliases()がクラッシュしない。"""
    list_aliases()
    captured = capsys.readouterr()
    assert "gdp" in captured.out


# ── fetch_worldbank_data (mocked wbgapi) ─────────────────────────────────────

def _mock_wb_dataframe() -> pd.DataFrame:
    """wbgapi.data.DataFrameが返すような形のPandas DataFrameを生成する。"""
    df = pd.DataFrame(
        {
            "Economy": ["JPN", "USA"],
            "Country": ["Japan", "United States"],
            "YR2022": [4.23e12, 2.5e13],
            "YR2023": [4.21e12, 2.7e13],
        }
    )
    df.set_index("Economy", inplace=True)
    return df


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_gdp_saves_csv(mock_wb: MagicMock, tmp_path: Path) -> None:
    """正常系: GDPデータをCSVに保存する。"""
    mock_wb.return_value = _mock_wb_dataframe()

    out = str(tmp_path / "wb_test.csv")
    fetch_worldbank_data("gdp", countries="JPN,USA", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8-sig")
    assert "Economy" in content or "JPN" in content


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_alias_resolves_to_indicator_code(mock_wb: MagicMock, tmp_path: Path) -> None:
    """エイリアス 'gdp' が正しいインジケーターコードに変換される。"""
    mock_wb.return_value = _mock_wb_dataframe()

    fetch_worldbank_data("gdp", output_file=str(tmp_path / "wb.csv"))

    call_args = mock_wb.call_args[0]
    assert INDICATORS["gdp"] in call_args[0]


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_multiple_indicators(mock_wb: MagicMock, tmp_path: Path) -> None:
    """カンマ区切りで複数インジケーターを受け付ける。"""
    mock_wb.return_value = _mock_wb_dataframe()

    fetch_worldbank_data("gdp,population", output_file=str(tmp_path / "wb_multi.csv"))

    call_args = mock_wb.call_args[0]
    assert len(call_args[0]) == 2


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_empty_data_no_csv(mock_wb: MagicMock, tmp_path: Path) -> None:
    """データが空のときCSVを生成しない。"""
    mock_wb.return_value = pd.DataFrame()

    out = str(tmp_path / "wb_empty.csv")
    fetch_worldbank_data("gdp", output_file=out)

    assert not Path(out).exists()


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_api_error_raises(mock_wb: MagicMock, tmp_path: Path) -> None:
    """wbgapiエラーは握り潰さず送出する（以前は print して None を返していた）。"""
    mock_wb.side_effect = RuntimeError("API unavailable")

    out = str(tmp_path / "wb_err.csv")
    with pytest.raises(RuntimeError, match="API unavailable"):
        fetch_worldbank_data("gdp", output_file=out)

    assert not Path(out).exists()


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_returns_polars_dataframe(
    mock_wb: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """戻り値は pl.DataFrame。output_file 無し(Hub 経由)なら既定名 CSV を勝手に書かない。"""
    monkeypatch.chdir(tmp_path)
    mock_wb.return_value = _mock_wb_dataframe()

    df = fetch_worldbank_data("gdp", countries="JPN,USA")

    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["Economy", "Country", "YR2022", "YR2023"]
    assert df["Economy"].to_list() == ["JPN", "USA"]
    assert list(tmp_path.iterdir()) == []


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_missing_values_become_null(mock_wb: MagicMock) -> None:
    raw = _mock_wb_dataframe()
    raw.loc["JPN", "YR2023"] = float("nan")
    mock_wb.return_value = raw
    df = fetch_worldbank_data("gdp")
    assert df["YR2023"].to_list()[0] is None


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_csv_write_error_propagates(mock_wb: MagicMock, tmp_path: Path) -> None:
    """CSV 書き出しの失敗を握り潰さない（出力先がディレクトリ）。"""
    mock_wb.return_value = _mock_wb_dataframe()
    with pytest.raises(OSError):
        fetch_worldbank_data("gdp", output_file=str(tmp_path))


@patch("worldbank_fetcher.wb.data.DataFrame")
def test_fetch_with_year_range(mock_wb: MagicMock, tmp_path: Path) -> None:
    """start/end年を指定するとrange()が渡される。"""
    mock_wb.return_value = _mock_wb_dataframe()

    fetch_worldbank_data("gdp", start_year=2020, end_year=2022,
                         output_file=str(tmp_path / "wb_yr.csv"))

    call_kwargs = mock_wb.call_args[1]
    assert "time" in call_kwargs
    assert list(call_kwargs["time"]) == [2020, 2021, 2022]
