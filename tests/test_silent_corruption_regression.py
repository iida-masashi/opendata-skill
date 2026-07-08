"""Regression tests for the 'silently corrupts data' bugs (2026 audit, group 1c)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from feature_engineer import engineer_features
from odpt_fetcher import fetch_odpt_data
from semicon_fetcher import compute_book_to_bill
from worldbank_fetcher import fetch_worldbank_data


# --- feature_engineer: non-ISO string dates must parse, not silently null out ---
def test_feature_engineer_parses_yyyymm_dates() -> None:
    df = pl.DataFrame({"d": ["202401", "202402", "202403", "202404"], "y": [1.0, 2.0, 3.0, 4.0]})
    out = engineer_features(df, date_col="d", target_col="y", lags=[1], rolling_windows=[2])
    assert out["d"].dtype == pl.Date
    assert out["d"].null_count() == 0
    assert out["day_of_week"].null_count() == 0  # calendar features not all-null


def test_feature_engineer_raises_on_unparseable_dates() -> None:
    df = pl.DataFrame({"d": ["not-a-date", "still-not"], "y": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Could not parse date column"):
        engineer_features(df, date_col="d", target_col="y")


def test_feature_engineer_respects_explicit_format() -> None:
    df = pl.DataFrame({"d": ["20240101", "20240201"], "y": [1.0, 2.0]})
    out = engineer_features(df, date_col="d", target_col="y", date_format="%Y%m%d", lags=[1])
    assert out["d"].null_count() == 0


# --- worldbank: a partial year range must be honored, not widened to 'all' ---
@patch("worldbank_fetcher.wb")
def test_worldbank_partial_start_only_builds_range(mock_wb: MagicMock, tmp_path: Path) -> None:
    fake = MagicMock()
    fake.empty = False
    fake.reset_index.return_value = None
    mock_wb.data.DataFrame.return_value = fake

    fetch_worldbank_data("gdp", countries="JPN", start_year=2015, output_file=str(tmp_path / "o.csv"))

    time_arg = mock_wb.data.DataFrame.call_args[1]["time"]
    assert isinstance(time_arg, range)
    assert min(time_arg) == 2015          # honored, not 'all'
    assert time_arg != "all"


@patch("worldbank_fetcher.wb")
def test_worldbank_no_range_still_all(mock_wb: MagicMock, tmp_path: Path) -> None:
    fake = MagicMock()
    fake.empty = False
    mock_wb.data.DataFrame.return_value = fake
    fetch_worldbank_data("gdp", countries="JPN", output_file=str(tmp_path / "o.csv"))
    assert mock_wb.data.DataFrame.call_args[1]["time"] == "all"


# --- semicon: book-to-bill must guard against zero shipments (no inf) ---
@patch("semicon_fetcher.fetch_semicon_data")
def test_semicon_b2b_zero_shipments_is_null_not_inf(mock_fetch: MagicMock) -> None:
    orders = pl.DataFrame({"date": ["2024-01", "2024-02"], "value": [100.0, 200.0]})
    ships = pl.DataFrame({"date": ["2024-01", "2024-02"], "value": [0.0, 100.0]})
    mock_fetch.side_effect = [orders, ships]

    df = compute_book_to_bill()
    b2b = df.sort("date")["book_to_bill"].to_list()
    assert b2b[0] is None                 # was inf (100/0)
    assert b2b[1] == pytest.approx(2.0)
    # no inf anywhere
    assert not df["book_to_bill"].is_infinite().any()


# --- odpt: nested list/struct fields must serialize to CSV, not crash ---
@patch("odpt_fetcher.requests.get")
def test_odpt_nested_json_writes_csv(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODPT_API_KEY", "dummy")
    resp = MagicMock()
    resp.json.return_value = [
        {
            "owl:sameAs": "odpt.BusTimetable:Toei.X",
            "odpt:busTimetableObject": [
                {"odpt:departureTime": "08:00", "odpt:busstopPole": "A"},
                {"odpt:departureTime": "08:30", "odpt:busstopPole": "B"},
            ],
        }
    ]
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "odpt.csv")
    fetch_odpt_data("odpt:BusTimetable", output_file=out)

    assert Path(out).exists()             # was: no file (write_csv crashed on nested)
    content = Path(out).read_text(encoding="utf-8")
    assert "departureTime" in content     # nested object serialized into the cell
