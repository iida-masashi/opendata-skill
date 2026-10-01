"""Tests for semicon_fetcher.py (FRED経由、実API)."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from semicon_fetcher import SEMI_SERIES, compute_book_to_bill, fetch_semicon_data


def test_semi_series_defined() -> None:
    for key in ["us_semi_shipments", "us_semi_inventories", "us_semi_ship_val"]:
        assert key in SEMI_SERIES


@pytest.mark.skipif(not os.getenv("FRED_API_KEY"), reason="FRED_API_KEY not set")
@pytest.mark.integration
def test_real_fred_semi_shipments(tmp_path: Path) -> None:
    """実API: 半導体新規受注の取得。"""
    out = str(tmp_path / "semi_real.csv")
    df = fetch_semicon_data(
        series="us_semi_shipments",
        start_date="2023-01-01",
        end_date="2023-12-31",
        output_file=out,
    )
    assert isinstance(df, pl.DataFrame)


@pytest.mark.skipif(not os.getenv("FRED_API_KEY"), reason="FRED_API_KEY not set")
@pytest.mark.integration
def test_real_book_to_bill() -> None:
    """実API: B2B比が正しく計算される。"""
    df = compute_book_to_bill(
        start_date="2023-01-01", end_date="2023-12-31",
    )
    assert isinstance(df, pl.DataFrame)
    if not df.is_empty():
        assert "book_to_bill" in df.columns
        assert "new_orders" in df.columns
        assert "shipments" in df.columns


@patch("fred_fetcher.requests.get")
def test_mock_semicon_parse(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: FRED JSONをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "observations": [
            {"date": "2023-01-01", "value": "5000.0"},
            {"date": "2023-02-01", "value": "5200.0"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    monkeypatch.setenv("FRED_API_KEY", "test_key_mock")

    out = str(tmp_path / "semi_mock.csv")
    df = fetch_semicon_data(series="us_semi_shipments", output_file=out)
    assert df.height == 2


@patch("semicon_fetcher.fetch_semicon_data")
def test_mock_book_to_bill_calc(mock_fetch: MagicMock) -> None:
    """モック: B2B比の計算ロジック確認。"""
    orders_df = pl.DataFrame({
        "date": ["2023-01-01", "2023-02-01"],
        "value": [100.0, 120.0],
        "series": ["us_semi_shipments", "us_semi_shipments"],
        "series_id": ["A34SNO", "A34SNO"],
    })
    ships_df = pl.DataFrame({
        "date": ["2023-01-01", "2023-02-01"],
        "value": [80.0, 100.0],
        "series": ["us_semi_ship_val", "us_semi_ship_val"],
        "series_id": ["A34SVS", "A34SVS"],
    })
    mock_fetch.side_effect = [orders_df, ships_df]

    df = compute_book_to_bill()
    assert df.height == 2
    b2b = df.get_column("book_to_bill").to_list()
    assert abs(b2b[0] - 1.25) < 1e-9
    assert abs(b2b[1] - 1.20) < 1e-9


@patch("semicon_fetcher.fetch_semicon_data")
def test_book_to_bill_has_value_column_for_hub_contract(mock_fetch: MagicMock) -> None:
    """Hub の date/value 契約: B2B比は value 列としても返る（既存の book_to_bill 列も維持）。"""
    mock_fetch.side_effect = [
        pl.DataFrame({"date": ["2023-01-01"], "value": [100.0]}),
        pl.DataFrame({"date": ["2023-01-01"], "value": [80.0]}),
    ]
    df = compute_book_to_bill()
    assert "value" in df.columns
    assert df["value"].to_list() == df["book_to_bill"].to_list()
    for col in ["date", "new_orders", "shipments", "book_to_bill", "series"]:
        assert col in df.columns


def test_semi_shipments_alias_points_to_shipments_series() -> None:
    """FRED: A34SNO=New Orders, A34SVS=Value of Shipments (Computers and Electronic Products)。"""
    assert SEMI_SERIES["us_semi_shipments"] == "A34SVS"
    assert SEMI_SERIES["us_semi_new_orders"] == "A34SNO"


@patch("fred_fetcher.requests.get")
def test_book_to_bill_uses_orders_over_shipments(
    mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch, make_response
) -> None:
    """B2B比 = 新規受注(A34SNO) / 出荷(A34SVS)。系列の取り違えで常に1.0にならないこと。"""
    monkeypatch.setenv("FRED_API_KEY", "test_key_mock")
    values = {"A34SNO": "120.0", "A34SVS": "100.0"}

    def _resp(url: str, **kwargs):
        sid = kwargs["params"]["series_id"]
        return make_response(json={"observations": [{"date": "2023-01-01", "value": values[sid]}]})

    mock_get.side_effect = _resp
    df = compute_book_to_bill()
    assert df["book_to_bill"].to_list() == [pytest.approx(1.2)]
