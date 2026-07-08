"""Tests for oecd_fetcher.py (OECD SDMX-JSON API)."""
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from oecd_fetcher import OECD_DATASETS, fetch_oecd_data, parse_sdmx_json


# --- Minimal SDMX-JSON V2 mock payload ---
def _make_sdmx_payload(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """2次元(REF_AREA × TIME_PERIOD)のSDMX-JSONペイロードを生成する。"""
    return {
        "data": {
            "structures": [
                {
                    "dimensions": {
                        "observation": [
                            {
                                "id": "REF_AREA",
                                "values": [{"id": "JPN"}, {"id": "USA"}],
                            },
                            {
                                "id": "TIME_PERIOD",
                                "values": [{"id": "2022"}, {"id": "2023"}],
                            },
                        ]
                    }
                }
            ],
            "dataSets": [
                {
                    "observations": {
                        "0:0": [100.0],
                        "0:1": [110.0],
                        "1:0": [200.0],
                        "1:1": [210.0],
                    }
                }
            ],
        }
    }


# ── parse_sdmx_json unit tests ──────────────────────────────────────────────

def test_parse_sdmx_json_returns_dataframe() -> None:
    """parse_sdmx_jsonが正しくDataFrameを返す。"""
    df = parse_sdmx_json(_make_sdmx_payload())
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 4


def test_parse_sdmx_json_columns() -> None:
    """REF_AREA, TIME_PERIOD, Value列が含まれる。"""
    df = parse_sdmx_json(_make_sdmx_payload())
    assert "REF_AREA" in df.columns
    assert "TIME_PERIOD" in df.columns
    assert "Value" in df.columns


def test_parse_sdmx_json_values() -> None:
    """JPN/2022 の Value が 100.0 であること。"""
    df = parse_sdmx_json(_make_sdmx_payload())
    row = df.filter(
        (pl.col("REF_AREA") == "JPN") & (pl.col("TIME_PERIOD") == "2022")
    )
    assert row["Value"][0] == pytest.approx(100.0)


def test_parse_sdmx_json_invalid_structure_raises() -> None:
    """不正なJSONはValueErrorを送出する。"""
    with pytest.raises(ValueError):
        parse_sdmx_json({"bad": "data"})


def test_parse_sdmx_json_empty_observations() -> None:
    """observationsが空のときは空のDataFrameを返す。"""
    payload = _make_sdmx_payload()
    payload["data"]["dataSets"][0]["observations"] = {}
    df = parse_sdmx_json(payload)
    assert df.is_empty()


# ── OECD_DATASETS mapping tests ─────────────────────────────────────────────

def test_oecd_datasets_keys_exist() -> None:
    """主要なデータセットコードが定義されている。"""
    for code in ["MEI", "KEI", "QNA", "TUD", "CLI"]:
        assert code in OECD_DATASETS
        assert "full_id" in OECD_DATASETS[code]


# ── fetch_oecd_data integration (mocked HTTP) ───────────────────────────────

@patch("oecd_fetcher.requests.get")
def test_fetch_oecd_saves_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: APIレスポンスをCSVに保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_sdmx_payload()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "oecd_test.csv")
    fetch_oecd_data("MEI", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text()
    assert "REF_AREA" in content
    assert "JPN" in content


@patch("oecd_fetcher.requests.get")
def test_fetch_oecd_country_filter(mock_get: MagicMock, tmp_path: Path) -> None:
    """countries引数でJPN以外をフィルタリングできる。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_sdmx_payload()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "oecd_jpn.csv")
    fetch_oecd_data("MEI", countries="JPN", output_file=out)

    content = Path(out).read_text()
    assert "JPN" in content
    assert "USA" not in content


@patch("tenacity.nap.sleep", lambda *_a, **_k: None)
@patch("oecd_fetcher.requests.get")
def test_fetch_oecd_transient_error_retried_then_raised(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    """一時的なネットワークエラーはリトライされ、枯渇後は送出される（黙って握り潰さない）。"""
    import requests

    mock_get.side_effect = requests.exceptions.Timeout("Timeout")

    out = str(tmp_path / "oecd_err.csv")
    with pytest.raises(requests.exceptions.Timeout):
        fetch_oecd_data("MEI", output_file=out)

    assert not Path(out).exists()
    # @retry_with_ratelimit が 5 回まで再試行する
    assert mock_get.call_count == 5


@patch("oecd_fetcher.requests.get")
def test_fetch_oecd_unknown_dataset_still_tries(mock_get: MagicMock, tmp_path: Path) -> None:
    """未知のデータセットコードでもAPIリクエストを試みる。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_sdmx_payload()
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "oecd_custom.csv")
    fetch_oecd_data("CUSTOM.DATASET,V1.0", output_file=out)

    assert mock_get.called
