"""feature_engineer の fail-loud 回帰テスト（2026 リファクタリング G5）。"""
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from feature_engineer import engineer_features

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "feature_engineer.py"


def test_partially_parseable_dates_raise_instead_of_interpolating() -> None:
    df = pl.DataFrame({"d": ["2024-01-01", "2024-01-02", "bogus"], "y": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="Could not parse date column"):
        engineer_features(df, date_col="d", target_col="y")


def test_explicit_format_must_parse_all_rows() -> None:
    df = pl.DataFrame({"d": ["20240101", "2024-02-01"], "y": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Could not parse date column"):
        engineer_features(df, date_col="d", target_col="y", date_format="%Y%m%d")


def test_cli_failure_exits_nonzero(tmp_path: Path) -> None:
    csv = tmp_path / "in.csv"
    csv.write_text("d,y\nbogus,1\nworse,2\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(csv), "--date_col", "d", "--target_col", "y"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert r.returncode != 0
    assert "Could not parse date column" in r.stderr
