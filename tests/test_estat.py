"""Tests for estat_fetcher.py (e-Stat Japanese government statistics API).

API キーが不要なロジックテストと、モックを使った結合テストを行う。
ESTAT_API_KEY 環境変数が未設定の場合も全テストが通過する。
"""
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from estat_fetcher import fetch_estat_data


def _make_estat_response(num_items: int = 3) -> dict[str, Any]:
    """e-Stat APIの正常レスポンスを生成する。"""
    items = []
    for i in range(num_items):
        items.append({
            "@tab": "001",
            "@cat01": f"C{i:03d}",
            "@area": "13000",
            "@time": f"202{i}01",
            "$": str(100 + i * 10),
        })

    return {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": 0, "ERROR_MSG": "正常終了", "DATE": "2024-01-01"},
            "PARAMETER": {},
            "STATISTICAL_DATA": {
                "RESULT_INF": {"TOTAL_NUMBER": str(num_items)},
                "TABLE_INF": {},
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {
                            "@id": "tab",
                            "@name": "表章項目",
                            "CLASS": [{"@code": "001", "@name": "数値"}],
                        },
                        {
                            "@id": "area",
                            "@name": "地域",
                            "CLASS": [{"@code": "13000", "@name": "東京都"}],
                        },
                        {
                            "@id": "time",
                            "@name": "時間軸（年次）",
                            "CLASS": [
                                {"@code": f"202{i}01", "@name": f"202{i}年"}
                                for i in range(num_items)
                            ],
                        },
                    ]
                },
                "DATA_INF": {"VALUE": items},
            },
        }
    }


@patch("estat_fetcher.requests.get")
def test_fetch_estat_saves_csv(mock_get: MagicMock, tmp_path: Path) -> None:
    """正常系: e-StatデータをCSVに保存する。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_estat_response(3)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "estat_test.csv")
    fetch_estat_data("dummy_app_id", "0003999999", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8")
    assert len(content) > 0


@patch("estat_fetcher.requests.get")
def test_fetch_estat_csv_has_value_column(mock_get: MagicMock, tmp_path: Path) -> None:
    """CSVにvalue列が含まれる。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_estat_response(2)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    out = str(tmp_path / "estat_val.csv")
    fetch_estat_data("dummy_app_id", "0003999999", output_file=out)

    content = Path(out).read_text(encoding="utf-8")
    assert "value" in content


@patch("estat_fetcher.requests.get")
def test_fetch_estat_passes_app_id(mock_get: MagicMock, tmp_path: Path) -> None:
    """appIdがAPIリクエストのparamsに含まれる。"""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_estat_response(1)
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    fetch_estat_data("MY_APP_ID_123", "0003999999", output_file=str(tmp_path / "out.csv"))

    call_kwargs = mock_get.call_args[1]["params"]
    assert call_kwargs["appId"] == "MY_APP_ID_123"


@patch("estat_fetcher.requests.get")
def test_fetch_estat_network_error_exits(mock_get: MagicMock, tmp_path: Path) -> None:
    """ネットワークエラー時はSystemExitを送出する（sys.exit(1)）。"""
    import requests as req_mod
    mock_get.side_effect = req_mod.exceptions.RequestException("Timeout")

    with pytest.raises(SystemExit):
        fetch_estat_data("dummy", "0003999999", output_file=str(tmp_path / "out.csv"))


@patch("estat_fetcher.requests.get")
def test_fetch_estat_api_status_error_exits(mock_get: MagicMock, tmp_path: Path) -> None:
    """APIがSTATUS!=0を返した場合はSystemExitを送出する。"""
    error_response = {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": 1, "ERROR_MSG": "Not found", "DATE": "2024-01-01"},
            "STATISTICAL_DATA": {},
        }
    }
    mock_response = MagicMock()
    mock_response.json.return_value = error_response
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with pytest.raises(SystemExit):
        fetch_estat_data("dummy", "INVALID_ID", output_file=str(tmp_path / "out.csv"))
