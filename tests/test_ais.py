"""Tests for ais_fetcher.py (AISキー未設定想定 → モック中心)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ais_fetcher import MAJOR_PORTS, fetch_ais_data, fetch_ais_datalastic


def test_major_ports_defined() -> None:
    """主要港湾が定義されている。"""
    for port in ["shanghai", "singapore", "rotterdam", "los_angeles", "suez"]:
        assert port in MAJOR_PORTS
        p = MAJOR_PORTS[port]
        assert "lat" in p and "lon" in p and "radius_km" in p


def test_major_ports_coordinates_sane() -> None:
    """座標が地理的に妥当な範囲。"""
    for port, p in MAJOR_PORTS.items():
        assert -90 <= p["lat"] <= 90, f"{port} lat out of range"
        assert -180 <= p["lon"] <= 180, f"{port} lon out of range"
        assert 0 < p["radius_km"] < 100


@patch("ais_fetcher.requests.get")
def test_mock_datalastic(mock_get: MagicMock) -> None:
    """モック: Datalastic APIレスポンスをパース。"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "vessels": [
                {"mmsi": 123456789, "name": "VESSEL A", "type": "cargo", "lat": 31.23, "lon": 121.47},
                {"mmsi": 987654321, "name": "VESSEL B", "type": "tanker", "lat": 31.24, "lon": 121.48},
            ]
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_ais_datalastic("shanghai", "fake_api_key", vessel_type="cargo")
    assert df.height == 2


def test_datalastic_unknown_port() -> None:
    """未知の港湾名でValueError。"""
    with pytest.raises(ValueError, match="Unknown port"):
        fetch_ais_datalastic("atlantis", "fake_key")


@patch("ais_fetcher.fetch_ais_datalastic")
def test_mock_integration_with_key(mock_fetcher: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: DATALASTIC_API_KEYがある場合、Datalastic経由で取得。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "test_key")
    mock_fetcher.return_value = pl.DataFrame({
        "mmsi": [111, 222],
        "name": ["A", "B"],
        "type": ["cargo", "tanker"],
    })

    out = str(tmp_path / "ais.csv")
    df = fetch_ais_data(port="shanghai", provider="datalastic", output_file=out)
    assert df.height == 2
    assert Path(out).exists()


def test_fetch_ais_no_key_returns_empty(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """キー未設定時は親切なエラーメッセージを出し、空DataFrameを返す。"""
    monkeypatch.delenv("DATALASTIC_API_KEY", raising=False)
    monkeypatch.delenv("AISHUB_USERNAME", raising=False)

    df = fetch_ais_data(port="shanghai", provider="auto")
    assert df.is_empty()
    captured = capsys.readouterr()
    assert "DATALASTIC_API_KEY" in captured.out or "AISHUB_USERNAME" in captured.out


@patch("ais_fetcher.fetch_ais_datalastic")
def test_datalastic_failure_fallback_empty(
    mock_fetcher: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Datalastic失敗時にもクラッシュしない。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "bad_key")
    monkeypatch.delenv("AISHUB_USERNAME", raising=False)
    mock_fetcher.side_effect = Exception("auth failed")

    df = fetch_ais_data(port="shanghai", provider="datalastic")
    assert df.is_empty()
