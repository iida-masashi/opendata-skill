"""Tests that the hub consumes the fetcher's returned DataFrame directly
(no temp-CSV roundtrip).

The discriminating assertion: a returned df keeps its rich dtype (pl.Date),
whereas a CSV roundtrip would have stringified it (Utf8).
"""
import datetime as dt
from pathlib import Path
from types import ModuleType, SimpleNamespace

import polars as pl


from scripts.opendata_hub import OpenDataHub


def _install_fake_fetcher(hub: OpenDataHub, name: str, module: ModuleType) -> None:
    """Make hub._load_module(name) return our fake module."""
    hub.fetchers[name] = Path(f"{name}_fetcher.py")  # any path; load is patched
    hub._load_module = lambda n, _m=module, _real=hub._load_module: _m if n == name else _real(n)  # type: ignore[assignment]


def test_returned_df_dtype_preserved_no_csv_roundtrip(hub: OpenDataHub) -> None:
    """A fetcher returning a pl.DataFrame with a real Date column must reach the
    caller as pl.Date — proving the value did NOT go through CSV stringification."""
    returned = pl.DataFrame(
        {"date": [dt.date(2024, 1, 1), dt.date(2024, 1, 2)], "value": [1.0, 2.0]}
    )

    fake = SimpleNamespace()

    def fetch_freight_data(output_file=None, **kwargs):  # signature the hub calls
        # Deliberately DO NOT write output_file -> if hub fell back to CSV it'd be empty
        return returned

    fake.fetch_freight_data = fetch_freight_data
    _install_fake_fetcher(hub, "freight", fake)  # type: ignore[arg-type]

    df = hub.get_freight(tickers="BDRY")
    assert not df.is_empty()
    assert df["date"].dtype == pl.Date          # would be Utf8 via CSV roundtrip
    assert df["value"].dtype in (pl.Float64, pl.Float32)


def test_returned_df_is_normalized(hub: OpenDataHub) -> None:
    """Return path must apply the same date/value normalization as the CSV path."""
    returned = pl.DataFrame({"Date": ["2024-01-01"], "Close": [100.0]})

    fake = SimpleNamespace()
    fake.fetch_freight_data = lambda output_file=None, **kw: returned
    _install_fake_fetcher(hub, "freight", fake)  # type: ignore[arg-type]

    df = hub.get_freight(tickers="BDRY")
    assert "date" in df.columns
    assert "value" in df.columns


def test_pandas_return_is_converted(hub: OpenDataHub) -> None:
    """Some fetchers (yfinance-based) may return a pandas DataFrame."""
    import pandas as pd

    fake = SimpleNamespace()
    fake.fetch_freight_data = lambda output_file=None, **kw: pd.DataFrame(
        {"date": ["2024-01-01"], "value": [7.0]}
    )
    _install_fake_fetcher(hub, "freight", fake)  # type: ignore[arg-type]

    df = hub.get_freight(tickers="BDRY")
    assert isinstance(df, pl.DataFrame)
    assert df["value"][0] == 7.0
