"""Tests for the time-alignment layer (Phase 2 ④).

Resamples heterogeneous-frequency covariates onto a common forecast frequency
so they can be joined as model inputs.
"""
import datetime as dt
import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from time_align import align_frequency, align_many


def _daily(n: int, start: dt.date = dt.date(2024, 1, 1)) -> pl.DataFrame:
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    return pl.DataFrame({"date": dates, "value": [float(i) for i in range(n)]})


def test_downsample_daily_to_monthly_mean() -> None:
    df = _daily(60)  # Jan + most of Feb 2024
    out = align_frequency(df, freq="1mo", agg="mean")
    assert "date" in out.columns and "value" in out.columns
    assert out["date"].dtype == pl.Date
    # 60 daily rows from Jan 1 -> two month buckets (Jan, Feb)
    assert len(out) == 2
    # Jan mean = mean(0..30) = 15.0
    jan = out.filter(pl.col("date") == dt.date(2024, 1, 1))
    assert jan["value"][0] == pytest.approx(15.0)


def test_upsample_monthly_to_daily_forward_fill() -> None:
    monthly = pl.DataFrame(
        {"date": [dt.date(2024, 1, 1), dt.date(2024, 2, 1)], "value": [10.0, 20.0]}
    )
    out = align_frequency(monthly, freq="1d", agg="mean", upsample_fill="forward")
    assert len(out) == 32  # Jan 1 .. Feb 1 inclusive
    # mid-January should carry January's value (forward fill)
    midjan = out.filter(pl.col("date") == dt.date(2024, 1, 15))
    assert midjan["value"][0] == pytest.approx(10.0)


def test_string_date_column_is_parsed() -> None:
    df = pl.DataFrame({"date": ["2024-01-01", "2024-01-02"], "value": [1.0, 2.0]})
    out = align_frequency(df, freq="1d", agg="mean")
    assert out["date"].dtype == pl.Date
    assert len(out) == 2


def test_empty_df_returns_empty() -> None:
    out = align_frequency(pl.DataFrame(), freq="1mo")
    assert out.is_empty()


def test_align_many_joins_on_common_grid() -> None:
    weather = _daily(40)  # daily
    macro = pl.DataFrame(
        {"date": [dt.date(2024, 1, 1), dt.date(2024, 2, 1)], "value": [100.0, 200.0]}
    )
    merged = align_many(
        {"weather": weather, "macro": macro}, freq="1mo", agg="mean"
    )
    assert "date" in merged.columns
    assert "weather" in merged.columns
    assert "macro" in merged.columns
    assert len(merged) == 2  # Jan, Feb
    jan = merged.filter(pl.col("date") == dt.date(2024, 1, 1))
    assert jan["macro"][0] == pytest.approx(100.0)


def test_filter_col_isolates_one_series_before_aligning() -> None:
    """Multi-dim e-Stat tables (e.g. keiki: 系列×date) compose with align via filter."""
    raw = pl.DataFrame(
        {
            "date": ["202401", "202401", "202402", "202402"],
            "系列": ["先行指数", "一致指数", "先行指数", "一致指数"],
            "value": [100.0, 110.0, 101.0, 111.0],
        }
    )
    out = align_frequency(raw, freq="1mo", filter_col="系列", filter_val="先行指数")
    assert len(out) == 2
    jan = out.filter(pl.col("date") == dt.date(2024, 1, 1))
    assert jan["value"][0] == pytest.approx(100.0)  # only 先行指数, not averaged with 一致


def test_align_many_skips_degenerate_sources() -> None:
    good = _daily(40)
    empty = pl.DataFrame()
    merged = align_many({"good": good, "empty": empty}, freq="1mo")
    assert "good" in merged.columns
    assert "empty" not in merged.columns
