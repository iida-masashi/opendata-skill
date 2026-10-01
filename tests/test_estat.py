"""Tests for estat_fetcher.py (e-Stat Japanese government statistics API).

API キーが不要なロジックテストと、モックを使った結合テストを行う。
ESTAT_API_KEY 環境変数が未設定の場合も全テストが通過する。
"""
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from estat_fetcher import as_list, check_estat_result, fetch_estat_data
from scripts.opendata_hub import OpenDataHub


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
def test_fetch_estat_network_error_raises(mock_get: MagicMock, tmp_path: Path) -> None:
    """ネットワークエラーは sys.exit でなく例外として送出される。"""
    import requests as req_mod
    mock_get.side_effect = req_mod.exceptions.RequestException("boom")

    with pytest.raises(req_mod.exceptions.RequestException):
        fetch_estat_data("dummy", "0003999999", output_file=str(tmp_path / "out.csv"))


@patch("estat_fetcher.requests.get")
def test_fetch_estat_api_error_status_raises(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    """STATUS>=100 (エラー) は RuntimeError を送出する。"""
    mock_get.return_value = make_response(json={
        "GET_STATS_DATA": {"RESULT": {"STATUS": 100, "ERROR_MSG": "認証に失敗しました。"}}
    })
    out = tmp_path / "out.csv"
    with pytest.raises(RuntimeError, match="認証に失敗"):
        fetch_estat_data("dummy", "INVALID_ID", output_file=str(out))
    assert not out.exists()


@patch("estat_fetcher.requests.get")
def test_fetch_estat_no_data_status_returns_empty(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    """STATUS=1 (正常終了・該当データ無し) は空DFを返す（STATISTICAL_DATA が無い応答）。"""
    mock_get.return_value = make_response(json={
        "GET_STATS_DATA": {"RESULT": {"STATUS": 1, "ERROR_MSG": "正常に終了しましたが、該当データはありませんでした。"}}
    })
    out = tmp_path / "out.csv"
    df = fetch_estat_data("dummy", "0003999999", output_file=str(out))
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
    assert not out.exists()


@patch("estat_fetcher.requests.get")
def test_fetch_estat_status0_without_data_inf_raises(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={
        "GET_STATS_DATA": {"RESULT": {"STATUS": 0}, "STATISTICAL_DATA": {"CLASS_INF": {}}}
    })
    with pytest.raises(RuntimeError):
        fetch_estat_data("dummy", "0003999999")


@patch("estat_fetcher.requests.get")
def test_fetch_estat_returns_dataframe_and_uses_https(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=_make_estat_response(3))
    df = fetch_estat_data("dummy", "0003999999")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 3
    assert mock_get.call_args[0][0].startswith("https://")
    assert mock_get.call_args.kwargs["timeout"] > 0


@patch("estat_fetcher.requests.get")
def test_fetch_estat_no_output_file_writes_nothing(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_get.return_value = make_response(json=_make_estat_response(1))
    fetch_estat_data("dummy", "0003999999")
    assert list(tmp_path.iterdir()) == []


@patch("estat_fetcher.requests.get")
def test_fetch_estat_time_column_meets_hub_date_contract(mock_get: MagicMock, make_response) -> None:
    """時間軸の列名（例: '時間軸（年次）'）は Hub の date 正規化に乗らないので date 列を足す。"""
    mock_get.return_value = make_response(json=_make_estat_response(2))
    df = fetch_estat_data("dummy", "0003999999")
    assert "時間軸（年次）" in df.columns  # 既存列は維持
    normalized = OpenDataHub._normalize_df(df)
    assert "date" in normalized.columns
    assert normalized["date"].to_list() == df["時間軸（年次）"].to_list()


@patch("estat_fetcher.requests.get")
def test_fetch_estat_literal_time_column_not_duplicated(mock_get: MagicMock, make_response) -> None:
    """メタが無く列名がそのまま 'time' の場合は date を足さない（正規化で列名が衝突しない）。"""
    mock_get.return_value = make_response(json={
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": 0},
            "STATISTICAL_DATA": {"DATA_INF": {"VALUE": {"@time": "2024000101", "$": "1"}}},
        }
    })
    df = fetch_estat_data("dummy", "0003000000")
    assert "date" not in df.columns
    assert "date" in OpenDataHub._normalize_df(df).columns


@patch("api_utils.get_with_retry.retry.sleep")
@patch("estat_fetcher.requests.get")
def test_fetch_estat_5xx_retried_once_not_doubly(mock_get: MagicMock, _sleep: MagicMock, make_response) -> None:
    """関数全体のリトライと HTTP 層のリトライが二重にならない（5回で止まる）。"""
    import requests as req_mod
    mock_get.return_value = make_response(status=503)
    with pytest.raises(req_mod.exceptions.HTTPError):
        fetch_estat_data("dummy", "0003999999")
    assert mock_get.call_count == 5


@patch("estat_fetcher.requests.get")
def test_fetch_estat_csv_write_error_propagates(mock_get: MagicMock, make_response, tmp_path: Path) -> None:
    """CSV 書き出しの失敗を握り潰さない（出力先がディレクトリ）。"""
    mock_get.return_value = make_response(json=_make_estat_response(1))
    with pytest.raises(OSError):
        fetch_estat_data("dummy", "0003999999", output_file=str(tmp_path))


def test_check_estat_result_and_as_list() -> None:
    assert check_estat_result({"RESULT": {"STATUS": 0}}) is True
    assert check_estat_result({"RESULT": {"STATUS": "1"}}) is False
    with pytest.raises(RuntimeError):
        check_estat_result({"RESULT": {"STATUS": 101, "ERROR_MSG": "x"}})
    assert as_list({"a": 1}) == [{"a": 1}]
    assert as_list([1, 2]) == [1, 2]
    assert as_list(None) == []


@patch("estat_fetcher.requests.get")
def test_fetch_estat_note_markers_become_null(mock_get: MagicMock, make_response) -> None:
    """DATA_INF.NOTE で定義された特殊文字（秘匿 X・該当なし - 等）は値でなく欠測として null にする。

    下流の time_align は数値化できない値を例外にするため、e-Stat 仕様の記号は fetcher で確定欠測にする。
    """
    payload = _make_estat_response(3)
    data_inf = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]
    data_inf["VALUE"][1]["$"] = "X"
    data_inf["VALUE"][2]["$"] = "-"
    data_inf["NOTE"] = [
        {"@char": "X", "$": "数字が秘匿されているもの"},
        {"@char": "-", "$": "該当数値のないもの"},
    ]
    mock_get.return_value = make_response(json=payload)

    df = fetch_estat_data(app_id="k", stats_data_id="0000000001")
    assert df["value"].to_list() == ["100", None, None]
    assert df["value_note"].to_list() == [None, "X", "-"]


@patch("estat_fetcher.requests.get")
def test_fetch_estat_undeclared_non_numeric_value_is_kept(mock_get: MagicMock, make_response) -> None:
    """NOTE に無い文字は推測で消さない（下流で検出させる）。"""
    payload = _make_estat_response(2)
    payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"][1]["$"] = "?"
    mock_get.return_value = make_response(json=payload)

    df = fetch_estat_data(app_id="k", stats_data_id="0000000001")
    assert df["value"].to_list() == ["100", "?"]
    assert "value_note" not in df.columns
