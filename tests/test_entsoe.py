"""Tests for entsoe_fetcher.py (ENTSOE_API_KEY未設定想定 → モック中心)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from entsoe_fetcher import AREA_EIC, DOC_TYPES, fetch_entsoe_data


def test_area_eic_defined() -> None:
    for c in ["DE", "FR", "IT", "ES", "GB"]:
        assert c in AREA_EIC
        assert AREA_EIC[c].startswith("10Y")


def test_doc_types_defined() -> None:
    for t in ["load_actual", "load_forecast", "generation", "day_ahead_price"]:
        assert t in DOC_TYPES


ENTSOE_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0">
  <TimeSeries>
    <Period>
      <timeInterval>
        <start>2024-01-01T00:00Z</start>
        <end>2024-01-01T23:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point>
        <position>1</position>
        <quantity>42000.0</quantity>
      </Point>
      <Point>
        <position>2</position>
        <quantity>41500.0</quantity>
      </Point>
      <Point>
        <position>3</position>
        <quantity>41200.0</quantity>
      </Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


@patch("entsoe_fetcher.requests.get")
def test_mock_load_actual(mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """モック: ENTSO-E XMLレスポンスをパース。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = ENTSOE_XML_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    out = str(tmp_path / "entsoe.csv")
    df = fetch_entsoe_data(
        data_type="load_actual", country="DE",
        start_date="2024-01-01", end_date="2024-01-01",
        output_file=out,
    )
    assert df.height == 3
    assert "value" in df.columns
    assert df.get_column("value").to_list() == [42000.0, 41500.0, 41200.0]
    assert Path(out).exists()


@patch("entsoe_fetcher.requests.get")
def test_mock_day_ahead_price(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Day-ahead priceでin/outドメインが同じに指定される。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")

    mock_resp = MagicMock()
    mock_resp.text = "<Publication_MarketDocument></Publication_MarketDocument>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    fetch_entsoe_data(data_type="day_ahead_price", country="FR")
    params = mock_get.call_args[1]["params"]
    assert params["in_Domain"] == params["out_Domain"]


def test_fetch_unknown_data_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未定義のdata_typeでValueError。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    with pytest.raises(ValueError, match="Unknown data_type"):
        fetch_entsoe_data(data_type="bogus", country="DE")


@patch("entsoe_fetcher.requests.get")
def test_mock_http_error(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(text="401"))
    mock_get.return_value = mock_resp

    df = fetch_entsoe_data(data_type="load_actual", country="DE")
    assert df.is_empty()


@patch("entsoe_fetcher.requests.get")
def test_mock_empty_xml(mock_get: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """空のXMLでクラッシュしない。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_resp = MagicMock()
    mock_resp.text = "<Publication_MarketDocument></Publication_MarketDocument>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    df = fetch_entsoe_data(data_type="load_actual", country="DE")
    assert df.is_empty()
