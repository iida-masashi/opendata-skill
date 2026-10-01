"""Tests for entsoe_fetcher.py (ENTSOE_API_KEY未設定想定 → モック中心)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import requests


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
    assert [d.strftime("%H:%M") for d in df.get_column("date").to_list()] == ["00:00", "01:00", "02:00"]
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
def test_mock_http_error_raises_and_redacts_token(
    mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP エラーは空DFに化けず例外。securityToken（URL クエリ）をメッセージに出さない。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "SECRET_ENTSOE_TOKEN")
    mock_get.return_value = make_response(
        text="<html>Unauthorized</html>", status=401,
        url="https://web-api.tp.entsoe.eu/api?securityToken=SECRET_ENTSOE_TOKEN",
    )

    with pytest.raises(requests.exceptions.HTTPError) as exc_info:
        fetch_entsoe_data(data_type="load_actual", country="DE")
    assert "401" in str(exc_info.value)
    assert "SECRET_ENTSOE_TOKEN" not in str(exc_info.value)


ACK_NO_DATA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">
  <mRID>abc</mRID>
  <Reason>
    <code>999</code>
    <text>No matching data found for Data item ACTUAL_TOTAL_LOAD_R3 [17.1.A] (10Y1001A1001A83F) and interval 2024-01-01T00:00:00.000Z/2024-01-02T00:00:00.000Z.</text>
  </Reason>
</Acknowledgement_MarketDocument>
"""

ACK_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">
  <mRID>abc</mRID>
  <Reason>
    <code>999</code>
    <text>The amount of requested data exceeds allowed limit.</text>
  </Reason>
</Acknowledgement_MarketDocument>
"""


@pytest.mark.parametrize("status", [200, 400])
@patch("entsoe_fetcher.requests.get")
def test_ack_no_matching_data_is_empty(
    mock_get: MagicMock, status: int, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """「No matching data found」の Acknowledgement は（200 でも 400 でも）確定0件として空DF。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_get.return_value = make_response(text=ACK_NO_DATA_XML, status=status)

    df = fetch_entsoe_data(data_type="load_actual", country="DE")
    assert df.is_empty()


@patch("entsoe_fetcher.requests.get")
def test_ack_other_reason_raises(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 200 で返る「0件」以外の Acknowledgement は例外（空DFに化けない）。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_get.return_value = make_response(text=ACK_ERROR_XML)

    with pytest.raises(RuntimeError, match="exceeds allowed limit"):
        fetch_entsoe_data(data_type="load_actual", country="DE")


# 発電量 (A75): 電源種別ごとの TimeSeries。B16 は Period が2つあり、2つ目は position 2,3 が省略されている。
ENTSOE_GENERATION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <mRID>1</mRID>
    <inBiddingZone_Domain.mRID codingScheme="A01">10Y1001A1001A83F</inBiddingZone_Domain.mRID>
    <MktPSRType>
      <psrType>B16</psrType>
    </MktPSRType>
    <Period>
      <timeInterval>
        <start>2024-01-01T00:00Z</start>
        <end>2024-01-01T00:30Z</end>
      </timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><quantity>10</quantity></Point>
      <Point><position>2</position><quantity>11</quantity></Point>
    </Period>
    <Period>
      <timeInterval>
        <start>2024-01-02T00:00Z</start>
        <end>2024-01-02T01:00Z</end>
      </timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><quantity>20</quantity></Point>
      <Point><position>4</position><quantity>23</quantity></Point>
    </Period>
  </TimeSeries>
  <TimeSeries>
    <mRID>2</mRID>
    <inBiddingZone_Domain.mRID codingScheme="A01">10Y1001A1001A83F</inBiddingZone_Domain.mRID>
    <MktPSRType>
      <psrType>B19</psrType>
    </MktPSRType>
    <Period>
      <timeInterval>
        <start>2024-01-01T00:00Z</start>
        <end>2024-01-01T02:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>500</quantity></Point>
      <Point><position>2</position><quantity>510</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""


def _fetch_generation(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> pl.DataFrame:
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_get.return_value = make_response(text=ENTSOE_GENERATION_XML)
    return fetch_entsoe_data(data_type="generation", country="DE", start_date="2024-01-01", end_date="2024-01-02")


@patch("entsoe_fetcher.requests.get")
def test_generation_keeps_psr_type(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> None:
    """電源種別 (psrType) が psr_type 列に残り、全電源が1つの value に混ざらない。"""
    df = _fetch_generation(mock_get, make_response, monkeypatch)
    assert "psr_type" in df.columns
    by_type = {r["psr_type"]: sorted(r["value"]) for r in df.group_by("psr_type").agg(pl.col("value")).iter_rows(named=True)}
    assert by_type["B19"] == [500.0, 510.0]
    assert by_type["B16"] == [10.0, 11.0, 20.0, 23.0]


@patch("entsoe_fetcher.requests.get")
def test_reads_all_periods(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> None:
    """TimeSeries 内の Period を全て読む（最初の1つで止まらない）。"""
    df = _fetch_generation(mock_get, make_response, monkeypatch)
    assert df.height == 6


@patch("entsoe_fetcher.requests.get")
def test_date_from_start_position_resolution(
    mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """date = Period start + (position-1) × resolution（省略された position があっても正しい時刻）。"""
    df = _fetch_generation(mock_get, make_response, monkeypatch)
    got = {(r["psr_type"], r["value"]): r["date"].strftime("%Y-%m-%dT%H:%M") for r in df.iter_rows(named=True)}
    assert got[("B16", 11.0)] == "2024-01-01T00:15"
    assert got[("B16", 23.0)] == "2024-01-02T00:45"
    assert got[("B19", 510.0)] == "2024-01-01T01:00"


@patch("entsoe_fetcher.requests.get")
def test_unsupported_resolution_raises(mock_get: MagicMock, make_response, monkeypatch: pytest.MonkeyPatch) -> None:
    """時刻を計算できない resolution は date を null にせず ValueError。"""
    monkeypatch.setenv("ENTSOE_API_KEY", "test_key_mock")
    mock_get.return_value = make_response(text=ENTSOE_XML_SAMPLE.replace("PT60M", "P1M"))

    with pytest.raises(ValueError, match="resolution"):
        fetch_entsoe_data(data_type="load_actual", country="DE")


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
