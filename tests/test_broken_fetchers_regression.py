"""Regression tests for the 5 broken-fetcher bugs found in the 2026 audit.

Each test pins the FIXED behavior; before the fix it would fail.
Style follows test_zipcode.py: mock requests.get.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import ais_fetcher
import comtrade_fetcher
from corp_fetcher import fetch_corporate_info
from eia_fetcher import fetch_eia_data
from estat_fetcher import fetch_estat_data
from gdelt_fetcher import fetch_gdelt_data
from jshis_fetcher import fetch_jshis_risk


# --- comtrade: partner "ALL" must map to M49 World "0", not the rejected "all" ---
def test_comtrade_all_maps_to_world_zero() -> None:
    assert comtrade_fetcher.COUNTRY_M49["ALL"] == "0"


# --- ais: LA / Long Beach longitudes must be western-hemisphere negative ---
def test_ais_us_ports_longitude_is_negative() -> None:
    assert ais_fetcher.MAJOR_PORTS["los_angeles"]["lon"] < 0
    assert ais_fetcher.MAJOR_PORTS["long_beach"]["lon"] < 0
    # sanity: still near 118W, and consistent with panama's signed convention
    assert ais_fetcher.MAJOR_PORTS["los_angeles"]["lon"] == pytest.approx(-118.264)
    assert ais_fetcher.MAJOR_PORTS["panama"]["lon"] < 0


# --- eia: crude_stocks and gasoline_stocks must issue DIFFERENT product facets ---
@patch("eia_fetcher.requests.get")
def test_eia_crude_and_gasoline_use_distinct_facets(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIA_API_KEY", "dummy")
    resp = MagicMock()
    resp.json.return_value = {"response": {"data": [{"period": "2024-01-01", "value": "1"}]}}
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    fetch_eia_data(series="crude_stocks", output_file=str(tmp_path / "c.csv"))
    crude_params = mock_get.call_args[1]["params"]

    fetch_eia_data(series="gasoline_stocks", output_file=str(tmp_path / "g.csv"))
    gas_params = mock_get.call_args[1]["params"]

    # Each must carry a series facet, and they must differ.
    assert crude_params.get("facets[series][]") == "WCESTUS1"
    assert gas_params.get("facets[series][]") == "WGTSTUS1"
    assert crude_params["facets[series][]"] != gas_params["facets[series][]"]


@patch("eia_fetcher.requests.get")
def test_eia_explicit_facet_is_not_overridden(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caller-supplied facets must win over the default."""
    monkeypatch.setenv("EIA_API_KEY", "dummy")
    resp = MagicMock()
    resp.json.return_value = {"response": {"data": [{"period": "2024-01-01", "value": "1"}]}}
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    fetch_eia_data(
        series="crude_stocks", facets={"product": "EPM0"}, output_file=str(tmp_path / "c.csv")
    )
    params = mock_get.call_args[1]["params"]
    assert params.get("facets[product][]") == "EPM0"
    assert "facets[series][]" not in params  # default not injected


# --- jshis: lowercase 'meshcode' key + correctly-shifted intensity codes ---
@patch("jshis_fetcher.requests.get")
def test_jshis_uses_correct_keys_and_intensity_mapping(
    mock_get: MagicMock, tmp_path: Path
) -> None:
    resp = MagicMock()
    resp.json.return_value = {
        "features": [
            {
                "properties": {
                    "meshcode": "5339",
                    "T30_I45_PS": "0.95",  # 5-lower
                    "T30_I50_PS": "0.80",  # 5-upper
                    "T30_I55_PS": "0.40",  # 6-lower
                    "T30_I60_PS": "0.10",  # 6-upper
                }
            }
        ]
    }
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "jshis.csv")
    fetch_jshis_risk(35.6895, 139.6917, output_file=out)

    content = Path(out).read_text(encoding="utf-8")
    rows = content.splitlines()
    header, values = rows[0].split(","), rows[1].split(",")
    row = dict(zip(header, values))

    # Values pass through as the raw API strings (not numerically parsed).
    assert row["MeshCode"] == "5339"            # was None (wrong key 'MESH_CODE')
    assert row["Prob_30Y_Int5L"] == "0.95"      # was mis-read from I50
    assert row["Prob_30Y_Int5U"] == "0.80"      # from I50 (was mis-read from I55)
    assert row["Prob_30Y_Int6L"] == "0.40"      # from I55 (was mis-read from I60)
    assert row["Prob_30Y_Int6U"] == "0.10"      # from I60 (was None, nonexistent I65)


# --- corp: NTA houjin-bangou type=12 is XML; must not call .json() / expect dict ---
def test_corp_does_not_request_json_type() -> None:
    """type=12 is XML per the official NTA spec; a JSON-only flow can never succeed.

    Pins that the fetcher no longer hard-codes the (nonexistent) JSON type=12 path.
    """
    import inspect

    src = inspect.getsource(fetch_corporate_info)
    # The misleading '# JSON format' comment and the .json() parse must be gone.
    assert "# JSON format" not in src
    assert "response.json()" not in src


@patch("corp_fetcher.requests.get")
def test_corp_parses_xml_response_to_csv(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """type=12 XML body must parse into a CSV (previously crashed on .json())."""
    monkeypatch.setenv("CORP_API_KEY", "dummy")
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<corporations><corporation>"
        b"<corporateNumber>1234567890123</corporateNumber>"
        b"<name>\xe6\xa0\xaa\xe5\xbc\x8f\xe4\xbc\x9a\xe7\xa4\xbe\xe3\x83\x86\xe3\x82\xb9\xe3\x83\x88</name>"
        b"</corporation></corporations>"
    )
    resp = MagicMock()
    resp.content = xml
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "corp.csv")
    fetch_corporate_info("1234567890123", mode="number", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8")
    assert "corporateNumber" in content
    assert "1234567890123" in content


@patch("corp_fetcher.requests.get")
def test_corp_parses_namespaced_xml(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A default xmlns on <corporations> must not silently break parsing."""
    monkeypatch.setenv("CORP_API_KEY", "dummy")
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<corporations xmlns="http://www.houjin-bangou.nta.go.jp">'
        b"<corporation><corporateNumber>9999999999999</corporateNumber>"
        b"<name>Test</name></corporation></corporations>"
    )
    resp = MagicMock()
    resp.content = xml
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "corp_ns.csv")
    fetch_corporate_info("9999999999999", mode="number", output_file=out)

    assert Path(out).exists()
    content = Path(out).read_text(encoding="utf-8")
    assert "9999999999999" in content
    assert "corporateNumber" in content  # namespace prefix stripped from tag


# --- estat: observation value must produce a single 'value' column, not '$' + 'value' ---
@patch("estat_fetcher.requests.get")
def test_estat_no_duplicate_value_column(
    mock_get: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = MagicMock()
    resp.json.return_value = {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": 0},
            "STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": []},
                "DATA_INF": {
                    "VALUE": [
                        {"@time": "2024000101", "@unit": "人", "$": "123"},
                    ]
                },
            },
        }
    }
    resp.raise_for_status.return_value = None
    mock_get.return_value = resp

    out = str(tmp_path / "estat.csv")
    fetch_estat_data("dummy", "0003000000", output_file=out)

    header = Path(out).read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "value" in header
    assert "$" not in header            # was a duplicate column carrying the same data
    assert header.count("value") == 1


# --- gdelt: empty timeline list must not IndexError ---
@patch("gdelt_fetcher._get_with_retry")
def test_gdelt_empty_timeline_no_indexerror(mock_get: MagicMock, tmp_path: Path) -> None:
    resp = MagicMock()
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = {"timeline": []}   # empty -> [0] would IndexError
    mock_get.return_value = resp

    out = str(tmp_path / "gdelt.csv")
    # Must return cleanly (empty df), not raise.
    df = fetch_gdelt_data(query="nonexistent", mode="timelinevolinfo", output_file=out)
    assert df.is_empty()
    assert not Path(out).exists()
