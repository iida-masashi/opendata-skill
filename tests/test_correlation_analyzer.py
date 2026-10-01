"""correlation_analyzer の回帰テスト（2026 リファクタリング G5）。"""
import os
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest  # noqa: E402

from correlation_analyzer import analyze_correlation  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "correlation_analyzer.py"
DATES = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def _csv(path: Path, rows: list[tuple[str, object]], header: str = "Date,value") -> str:
    path.write_text(header + "\n" + "\n".join(f"{d},{v}" for d, v in rows) + "\n", encoding="utf-8")
    return str(path)


def test_same_value_column_name_does_not_self_correlate(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", list(zip(DATES, [1, 2, 3, 4])))
    f2 = _csv(tmp_path / "b.csv", list(zip(DATES, [4, 3, 2, 1])))
    corr = analyze_correlation(f1, "value", f2, "value", output_img=str(tmp_path / "o.png"))
    assert corr == pytest.approx(-1.0)


def test_fallback_to_first_numeric_column_uses_each_file(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", list(zip(DATES, [1, 2, 3, 4])))
    f2 = _csv(tmp_path / "b.csv", list(zip(DATES, [4, 3, 2, 1])))
    corr = analyze_correlation(f1, None, f2, None, output_img=str(tmp_path / "o.png"))
    assert corr == pytest.approx(-1.0)


def test_unparseable_date_raises(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", [("2024-01-01", 1), ("bogus", 2), ("2024-01-03", 3)])
    f2 = _csv(tmp_path / "b.csv", [("2024-01-01", 1), ("2024-01-02", 2), ("2024-01-03", 3)])
    with pytest.raises(Exception, match=r"(?i)bogus|parse|conversion|strict"):
        analyze_correlation(f1, "value", f2, "value", output_img=str(tmp_path / "o.png"))


def test_constant_series_raises_instead_of_format_crash(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", list(zip(DATES, [5, 5, 5, 5])))
    f2 = _csv(tmp_path / "b.csv", list(zip(DATES, [1, 2, 3, 4])))
    with pytest.raises(ValueError, match="Correlation could not be computed"):
        analyze_correlation(f1, "value", f2, "value", output_img=str(tmp_path / "o.png"))


def test_explicit_missing_column_raises(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", list(zip(DATES, [1, 2, 3, 4])))
    f2 = _csv(tmp_path / "b.csv", list(zip(DATES, [1, 2, 3, 4])))
    with pytest.raises(KeyError, match="temperature"):
        analyze_correlation(f1, "temperature", f2, "value", output_img=str(tmp_path / "o.png"))


def test_no_common_dates_raises(tmp_path: Path) -> None:
    f1 = _csv(tmp_path / "a.csv", [("2024-01-01", 1), ("2024-01-02", 2)])
    f2 = _csv(tmp_path / "b.csv", [("2025-01-01", 1), ("2025-01-02", 2)])
    with pytest.raises(ValueError, match="No common dates"):
        analyze_correlation(f1, "value", f2, "value", output_img=str(tmp_path / "o.png"))


def test_cli_failure_exits_nonzero(tmp_path: Path) -> None:
    missing = str(tmp_path / "nope.csv")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), missing, missing, "--col1", "value", "--col2", "value"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode != 0
