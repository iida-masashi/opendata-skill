"""Tests for the time-alignment layer (Phase 2 ④).

Resamples heterogeneous-frequency covariates onto a common forecast frequency
so they can be joined as model inputs.
"""
import datetime as dt

import polars as pl
import pytest


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


# --- fail-loud regressions (2026 refactor, G5) ---
def test_missing_filter_col_raises() -> None:
    raw = pl.DataFrame({"date": ["202401"], "value": [1.0]})
    with pytest.raises(KeyError, match="系列"):
        align_frequency(raw, freq="1mo", filter_col="系列", filter_val="先行指数")


def test_missing_date_or_value_col_raises() -> None:
    with pytest.raises(KeyError, match="date"):
        align_frequency(pl.DataFrame({"d": ["2024-01-01"], "value": [1.0]}))
    with pytest.raises(KeyError, match="value"):
        align_frequency(pl.DataFrame({"date": ["2024-01-01"], "v": [1.0]}))


def test_align_many_raises_on_source_missing_columns() -> None:
    bad = pl.DataFrame({"d": [dt.date(2024, 1, 1)], "v": [1.0]})
    with pytest.raises(KeyError):
        align_many({"good": _daily(40), "bad": bad}, freq="1mo")


def test_non_numeric_values_raise_with_count() -> None:
    df = pl.DataFrame(
        {"date": ["2024-01-01", "2024-01-02", "2024-01-03"], "value": ["1", "x", "-"]}
    )
    with pytest.raises(ValueError, match="2 of 3"):
        align_frequency(df, freq="1d")


def test_originally_null_values_are_not_an_error() -> None:
    df = pl.DataFrame({"date": ["2024-01-01", "2024-01-02"], "value": ["1", None]})
    out = align_frequency(df, freq="1d")
    assert len(out) == 2


def test_unparseable_dates_raise_instead_of_dropping_rows() -> None:
    df = pl.DataFrame(
        {"date": ["2024-01-01", "2024-01-02", "bogus"], "value": [1.0, 2.0, 3.0]}
    )
    with pytest.raises(ValueError, match="Could not parse date column"):
        align_frequency(df, freq="1d")


def test_originally_null_dates_are_dropped_without_error() -> None:
    df = pl.DataFrame(
        {"date": ["2024-01-01", None, "2024-01-02"], "value": [1.0, 2.0, 3.0]}
    )
    out = align_frequency(df, freq="1d")
    assert len(out) == 2


def test_align_many_applies_per_source_filters() -> None:
    keiki = pl.DataFrame(
        {
            "date": ["202401", "202401", "202402", "202402"],
            "系列": ["先行指数", "一致指数", "先行指数", "一致指数"],
            "value": [100.0, 110.0, 101.0, 111.0],
        }
    )
    merged = align_many(
        {"keiki": keiki, "weather": _daily(40)},
        freq="1mo",
        filters={"keiki": ("系列", "先行指数")},
    )
    jan = merged.filter(pl.col("date") == dt.date(2024, 1, 1))
    assert jan["keiki"][0] == pytest.approx(100.0)


def test_align_many_rejects_filters_for_unknown_source() -> None:
    with pytest.raises(KeyError, match="kieki"):
        align_many({"keiki": _daily(10)}, filters={"kieki": ("系列", "先行指数")})


def test_parse_dates_requires_single_format_for_all_rows() -> None:
    from time_align import parse_dates

    s = pl.Series("d", ["202401", "202402"])
    assert parse_dates(s).to_list() == [dt.date(2024, 1, 1), dt.date(2024, 2, 1)]
    with pytest.raises(ValueError, match="Could not parse date column 'd'"):
        parse_dates(pl.Series("d", ["202401", "2024-02"]))


def test_filter_val_matching_no_rows_raises() -> None:
    """filter_val の打ち間違いでソースが黙って消えない（一致0件は例外）。"""
    df = pl.DataFrame({
        "date": ["2024-01-01", "2024-02-01"],
        "value": [1.0, 2.0],
        "series": ["leading", "leading"],
    })
    with pytest.raises(ValueError, match="matched no rows"):
        align_frequency(df, filter_col="series", filter_val="leadng")
