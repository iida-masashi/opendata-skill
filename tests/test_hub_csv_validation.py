"""Tests for OpenDataHub._csv_to_df hardening (Phase 2, features ① + ③).

① A CSV that exists but fails to parse must NOT be silently turned into an
   empty DataFrame (which reads as "no data" to every caller and to the cache).
③ A non-degenerate-schema guard: a CSV that parses but is all-null / has no
   usable column must be reported, not cached as if it were good covariate data.
"""
import sys
from pathlib import Path

import polars as pl
import pytest

# Hub uses a relative import (from .cache_manager); import it as a package
# member by putting the skill ROOT (parent of scripts/) on the path.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.opendata_hub import OpenDataHub  # noqa: E402


@pytest.fixture
def hub(tmp_path: Path) -> OpenDataHub:
    return OpenDataHub(cache_dir=str(tmp_path / "cache"))


def test_missing_file_is_empty_not_error(hub: OpenDataHub, tmp_path: Path) -> None:
    """No file written = legitimate 'no data' = empty df (unchanged contract)."""
    df = hub._csv_to_df(str(tmp_path / "nope.csv"))
    assert df.is_empty()


def test_valid_csv_normalizes_columns(hub: OpenDataHub, tmp_path: Path) -> None:
    p = tmp_path / "ok.csv"
    p.write_text("Date,Close\n2024-01-01,100\n2024-01-02,101\n", encoding="utf-8")
    df = hub._csv_to_df(str(p))
    assert "date" in df.columns
    assert "value" in df.columns
    assert len(df) == 2
    assert not p.exists()  # temp file cleaned up


def test_unparseable_existing_file_raises_not_silent_empty(
    hub: OpenDataHub, tmp_path: Path
) -> None:
    """A corrupt/non-CSV body that DID get written must surface as an error,
    not masquerade as empty 'no data'."""
    p = tmp_path / "broken.csv"
    # Ragged/garbage content that pl.read_csv cannot parse into a table.
    p.write_bytes(b"\x00\x01\x02 not a csv \xff\xfe\n\"unterminated")
    with pytest.raises(Exception):  # noqa: B017 - any parse error is acceptable
        hub._csv_to_df(str(p))


def test_close_and_adj_close_no_rename_collision(
    hub: OpenDataHub, tmp_path: Path
) -> None:
    """Both 'Close' and 'Adj Close' present must not collide into duplicate
    'value' columns (which would DuplicateError -> previously silent-empty)."""
    p = tmp_path / "yahoo.csv"
    p.write_text("Date,Close,Adj Close\n2024-01-01,100,99\n", encoding="utf-8")
    df = hub._csv_to_df(str(p))
    assert not df.is_empty()
    assert "value" in df.columns
    assert df.columns.count("value") == 1  # exactly one value column


# ③ schema / non-degeneracy guard ------------------------------------------

def test_validate_df_rejects_all_null(hub: OpenDataHub) -> None:
    bad = pl.DataFrame({"date": [None, None], "value": [None, None]})
    assert hub._is_degenerate(bad) is True


def test_validate_df_accepts_real_data(hub: OpenDataHub) -> None:
    good = pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})
    assert hub._is_degenerate(good) is False


def test_validate_df_empty_is_degenerate(hub: OpenDataHub) -> None:
    assert hub._is_degenerate(pl.DataFrame()) is True
