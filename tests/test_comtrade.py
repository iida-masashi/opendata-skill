"""Tests for comtrade_fetcher.py (モック中心: レートリミット厳しく本番呼び出し回避)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from comtrade_fetcher import COUNTRY_M49, fetch_comtrade_data


def test_country_m49_mapping() -> None:
    """主要国のM49コードが正しくマップされている。"""
    assert COUNTRY_M49["JP"] == "392"
    assert COUNTRY_M49["US"] == "842"
    assert COUNTRY_M49["CN"] == "156"


@patch("comtrade_fetcher.requests.get")
def test_mock_comtrade_response(mock_get: MagicMock, tmp_path: Path) -> None:
    """モック: Comtrade標準スキーマをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "period": "2023",
                "reporterISO": "JPN",
                "reporterDesc": "Japan",
                "partnerISO": "CHN",
                "partnerDesc": "China",
                "cmdCode": "8542",
                "cmdDesc": "Electronic integrated circuits",
                "flowCode": "M",
                "flowDesc": "Import",
                "primaryValue": 12345678.0,
                "netWgt": 1000.0,
                "qty": 500.0,
            },
            {
                "period": "2023",
                "reporterISO": "JPN",
                "reporterDesc": "Japan",
                "partnerISO": "TWN",
                "partnerDesc": "Taiwan",
                "cmdCode": "8542",
                "cmdDesc": "Electronic integrated circuits",
                "flowCode": "M",
                "flowDesc": "Import",
                "primaryValue": 9876543.0,
                "netWgt": 800.0,
                "qty": 400.0,
            },
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "comtrade.csv")
    df = fetch_comtrade_data(
        reporter="JP", partner="ALL", hs_code="8542",
        flow="M", period="2023", output_file=out,
    )
    assert df.height == 2
    # 標準化カラムが付与されている
    assert "date" in df.columns
    assert "value" in df.columns
    assert Path(out).exists()


@patch("comtrade_fetcher.requests.get")
def test_mock_country_resolution(mock_get: MagicMock) -> None:
    """ISO2コードがM49に変換されてリクエストされる。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_comtrade_data(reporter="JP", partner="CN", period="2023")
    params = mock_get.call_args[1]["params"]
    assert params["reporterCode"] == "392"  # Japan
    assert params["partnerCode"] == "156"   # China


@patch("comtrade_fetcher.requests.get")
def test_mock_empty_data(mock_get: MagicMock) -> None:
    """空データでクラッシュしない。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_comtrade_data(reporter="JP", period="2023")
    assert df.is_empty()


@patch("comtrade_fetcher.requests.get")
def test_mock_http_error_raises(mock_get: MagicMock, make_response) -> None:
    """HTTP 4xx は空DFでなく例外。API のエラー本文をメッセージに含める。"""
    mock_get.return_value = make_response(
        status=400, json={"error": "For monthly frequency, all periods must be in YYYYMM format."}
    )

    with pytest.raises(RuntimeError, match="HTTP 400.*YYYYMM"):
        fetch_comtrade_data(reporter="JP", period="2023")


@patch("api_utils.get_with_retry.retry.sleep")
@patch("comtrade_fetcher.requests.get")
def test_mock_rate_limit_is_retried(mock_get: MagicMock, _sleep: MagicMock, make_response) -> None:
    """無料枠のレート制限 (429) はリトライし、回復すればデータを返す。"""
    mock_get.side_effect = [
        make_response(status=429, text="rate limit"),
        make_response(json={"error": "", "data": [{"period": 2023, "primaryValue": 1.0}]}),
    ]

    df = fetch_comtrade_data(reporter="JP", period="2023")

    assert df.height == 1
    assert mock_get.call_count == 2


@patch("comtrade_fetcher.requests.get")
def test_mock_error_payload_raises(mock_get: MagicMock, make_response) -> None:
    """HTTP 200 でも error が空でなければ例外。"""
    mock_get.return_value = make_response(json={"error": "Invalid cmdCode", "data": None})

    with pytest.raises(RuntimeError, match="Invalid cmdCode"):
        fetch_comtrade_data(reporter="JP", period="2023")


@patch("comtrade_fetcher.requests.get")
def test_mock_empty_error_string_is_ok(mock_get: MagicMock, make_response) -> None:
    """正常応答の "error": "" はエラー扱いしない。"""
    mock_get.return_value = make_response(
        json={"elapsedTime": "0.6 secs", "count": 1, "error": "", "data": [{"period": "2023", "primaryValue": 5.0}]}
    )

    df = fetch_comtrade_data(reporter="JP", period="2023")
    assert df["value"].to_list() == [5.0]


@patch("comtrade_fetcher.requests.get")
def test_monthly_default_period_is_yyyymm(mock_get: MagicMock, make_response) -> None:
    """frequency='M' で period 未指定なら YYYYMM（前年12月）を送る（年 'YYYY' は API が 400 を返す）。"""
    mock_get.return_value = make_response(json={"error": "", "data": []})

    fetch_comtrade_data(reporter="JP", frequency="M")

    period = mock_get.call_args[1]["params"]["period"]
    assert len(period) == 6
    assert period.endswith("12")
    assert "/C/M/HS" in mock_get.call_args[0][0]


@patch("comtrade_fetcher.requests.get")
def test_annual_default_period_is_yyyy(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json={"error": "", "data": []})

    fetch_comtrade_data(reporter="JP")

    assert len(mock_get.call_args[1]["params"]["period"]) == 4


@pytest.mark.parametrize("role", ["reporter", "partner"])
@patch("comtrade_fetcher.requests.get")
def test_taiwan_alias_rejected(mock_get: MagicMock, role: str) -> None:
    """TW は Comtrade では reporter に存在せず、partner 158 は0件になる（490 Other Asia, nes に計上）。"""
    kwargs = {"reporter": "JP", "partner": "ALL", role: "TW"}

    with pytest.raises(ValueError, match="490"):
        fetch_comtrade_data(period="2023", **kwargs)
    mock_get.assert_not_called()


@patch("comtrade_fetcher.requests.get")
def test_no_output_file_writes_nothing(
    mock_get: MagicMock, make_response, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_get.return_value = make_response(json={"error": "", "data": [{"period": "2023", "primaryValue": 5.0}]})
    monkeypatch.chdir(tmp_path)

    fetch_comtrade_data(reporter="JP", period="2023")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("reporter", ["ALL", "all", "0"])
@patch("comtrade_fetcher.requests.get")
def test_world_reporter_rejected(mock_get: MagicMock, reporter: str) -> None:
    """0 (World) は Reporters.json に無く、報告国として送ると無効。相手国としての ALL は可。"""
    with pytest.raises(ValueError, match="partner='ALL'"):
        fetch_comtrade_data(reporter=reporter, period="2023")
    mock_get.assert_not_called()
