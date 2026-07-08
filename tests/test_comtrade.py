"""Tests for comtrade_fetcher.py (モック中心: レートリミット厳しく本番呼び出し回避)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

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
def test_mock_http_error(mock_get: MagicMock) -> None:
    """HTTPエラーで空DataFrame。"""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="rate limit"))
    mock_get.return_value = mock_resp

    df = fetch_comtrade_data(reporter="JP", period="2023")
    assert df.is_empty()
