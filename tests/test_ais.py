"""Tests for ais_fetcher.py (AISキー未設定想定 → モック中心)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest


from ais_fetcher import MAJOR_PORTS, fetch_ais_aishub, fetch_ais_data, fetch_ais_datalastic
from api_utils import MissingApiKeyError


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


def test_fetch_ais_no_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """キー未設定時は空DFではなく、取得方法つきの MissingApiKeyError。"""
    monkeypatch.delenv("DATALASTIC_API_KEY", raising=False)
    monkeypatch.delenv("AISHUB_USERNAME", raising=False)

    with pytest.raises(MissingApiKeyError) as exc_info:
        fetch_ais_data(port="shanghai", provider="auto")
    assert "DATALASTIC_API_KEY" in str(exc_info.value)
    assert "AISHUB_USERNAME" in str(exc_info.value)


@patch("ais_fetcher.fetch_ais_datalastic")
def test_datalastic_failure_propagates(
    mock_fetcher: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """キー設定済みで Datalastic が失敗したら、握り潰さず・「キー未設定」と誤案内せず例外を伝播。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "bad_key")
    monkeypatch.delenv("AISHUB_USERNAME", raising=False)
    mock_fetcher.side_effect = RuntimeError("auth failed")

    with pytest.raises(RuntimeError, match="auth failed"):
        fetch_ais_data(port="shanghai", provider="datalastic")


@pytest.mark.parametrize("provider", ["auto", "aishub", "datalastic"])
@patch("ais_fetcher.requests.get")
def test_unknown_port_raises_before_fetch(
    mock_get: MagicMock, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未登録の港は入口で ValueError。AISHub が bbox=None（全世界）で取得してしまわない。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    monkeypatch.setenv("AISHUB_USERNAME", "u")

    with pytest.raises(ValueError, match="Unknown port"):
        fetch_ais_data(port="atlantis", provider=provider)
    mock_get.assert_not_called()


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    with pytest.raises(ValueError, match="Unknown provider"):
        fetch_ais_data(port="shanghai", provider="marinetraffic")


@patch("ais_fetcher.requests.get")
def test_aishub_error_payload_raises(mock_get: MagicMock, make_response) -> None:
    """AISHub の [{"ERROR": true, ...}] 応答は空DFでなく例外。"""
    mock_get.return_value = make_response(
        json=[{"ERROR": True, "USERNAME": "AH_TEST_USER", "FORMAT": "HUMAN", "ERROR_MESSAGE": "Too frequent requests!"}]
    )

    with pytest.raises(RuntimeError, match="Too frequent requests"):
        fetch_ais_aishub("AH_TEST_USER", (31.0, 121.0, 31.5, 121.9))


@patch("ais_fetcher.requests.get")
def test_aishub_non_json_raises(mock_get: MagicMock, make_response) -> None:
    """AISHub の JSON パース失敗は空DFでなく例外。"""
    mock_get.return_value = make_response(text="<html>Service unavailable</html>")

    with pytest.raises(ValueError):
        fetch_ais_aishub("AH_TEST_USER", (31.0, 121.0, 31.5, 121.9))


@patch("ais_fetcher.requests.get")
def test_aishub_ok_parses_vessels(mock_get: MagicMock, make_response) -> None:
    mock_get.return_value = make_response(json=[
        {"ERROR": False, "USERNAME": "u", "FORMAT": "HUMAN", "RECORDS": 2},
        [{"MMSI": 1, "NAME": "A"}, {"MMSI": 2, "NAME": "B"}],
    ])

    df = fetch_ais_aishub("u", (31.0, 121.0, 31.5, 121.9))
    assert df.height == 2
    assert mock_get.call_args[1]["params"]["latmin"] == 31.0


@patch("ais_fetcher.fetch_ais_aishub")
@patch("ais_fetcher.fetch_ais_datalastic")
def test_auto_falls_back_to_aishub_with_port_bbox(
    mock_dl: MagicMock, mock_ah: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Datalastic が正常に0件なら AISHub にフォールバックし、港の bbox を必ず渡す。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    monkeypatch.setenv("AISHUB_USERNAME", "u")
    mock_dl.return_value = pl.DataFrame()
    mock_ah.return_value = pl.DataFrame({"MMSI": [1]})

    df = fetch_ais_data(port="shanghai", provider="auto")
    assert df.height == 1
    bbox = mock_ah.call_args[0][1]
    assert bbox is not None
    assert bbox[0] < MAJOR_PORTS["shanghai"]["lat"] < bbox[2]


@patch("ais_fetcher.fetch_ais_aishub")
@patch("ais_fetcher.fetch_ais_datalastic")
def test_auto_datalastic_error_falls_back_to_aishub(
    mock_dl: MagicMock, mock_hub: MagicMock, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """auto: Datalastic が例外でも AISHub のキーがあれば警告を出して AISHub で取得する。"""
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    monkeypatch.setenv("AISHUB_USERNAME", "u")
    mock_dl.side_effect = RuntimeError("datalastic down")
    mock_hub.return_value = pl.DataFrame({"mmsi": [1, 2]})

    df = fetch_ais_data(port="shanghai", provider="auto")
    assert df.height == 2
    assert "datalastic down" in capsys.readouterr().err


@patch("ais_fetcher.fetch_ais_aishub")
@patch("ais_fetcher.fetch_ais_datalastic")
def test_auto_both_providers_fail_raises(
    mock_dl: MagicMock, mock_hub: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    monkeypatch.setenv("AISHUB_USERNAME", "u")
    mock_dl.side_effect = RuntimeError("datalastic down")
    mock_hub.side_effect = RuntimeError("aishub down")

    with pytest.raises(RuntimeError, match="aishub down"):
        fetch_ais_data(port="shanghai", provider="auto")


@patch("ais_fetcher.fetch_ais_datalastic")
def test_auto_datalastic_error_without_aishub_raises(
    mock_dl: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "k")
    monkeypatch.delenv("AISHUB_USERNAME", raising=False)
    mock_dl.side_effect = RuntimeError("datalastic down")

    with pytest.raises(RuntimeError, match="datalastic down"):
        fetch_ais_data(port="shanghai", provider="auto")
