"""Tests for the e-Stat-backed JP preset hub methods (Phase 2 ⑧ + ⑪).

These wrap the existing e-Stat fetch path with verified statsDataIds:
  - get_keiki_di():        景気動向指数 (CI/DI, incl. 先行指数)  -> 0003446461
  - get_inbound_visitors(): 訪日外客数 (港別 入国外国人国籍・地域) -> 0003449064
"""
from pathlib import Path

import polars as pl
import pytest

from scripts.opendata_hub import OpenDataHub


def test_keiki_di_calls_estat_with_correct_id(
    hub: OpenDataHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESTAT_API_KEY", "dummy")
    captured = {}

    def fake_get_estat(stats_data_id, app_id=None, **kwargs):
        captured["id"] = stats_data_id
        return pl.DataFrame({"date": ["202401"], "value": [10.0]})

    hub.get_estat = fake_get_estat  # type: ignore[assignment]
    df = hub.get_keiki_di()
    assert captured["id"] == "0003446461"
    assert not df.is_empty()


def test_inbound_visitors_calls_estat_with_correct_id(
    hub: OpenDataHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ESTAT_API_KEY", "dummy")
    captured = {}

    def fake_get_estat(stats_data_id, app_id=None, **kwargs):
        captured["id"] = stats_data_id
        return pl.DataFrame({"date": ["202401"], "value": [100.0]})

    hub.get_estat = fake_get_estat  # type: ignore[assignment]
    df = hub.get_inbound_visitors()
    assert captured["id"] == "0003449064"
    assert not df.is_empty()


def test_get_boj_tankan_method(hub: OpenDataHub) -> None:
    """Hub convenience wrapper for the new BOJ fetcher dispatches correctly."""
    captured = {}

    class _FakeMod:
        @staticmethod
        def fetch_boj_data(output_file=None, **kwargs):
            captured.update(kwargs)
            return pl.DataFrame({"date": ["202601"], "value": [17.0]})

    fake_mod = _FakeMod()
    hub.fetchers["boj"] = Path("boj_fetcher.py")
    hub._load_module = lambda n: fake_mod  # type: ignore[assignment]

    df = hub.get_boj_tankan(series="tankan_large_mfg")
    assert captured.get("series") == "tankan_large_mfg"
    assert not df.is_empty()


def test_keiki_di_and_inbound_visitors_series_and_country_filters(
    hub: OpenDataHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_keiki_di(series=...) と get_inbound_visitors(country=...) のフィルタリング検証。"""
    monkeypatch.setenv("ESTAT_API_KEY", "dummy")

    def fake_get_estat(stats_data_id, app_id=None, **kwargs):
        if stats_data_id == "0003446461":
            return pl.DataFrame({
                "date": ["20240101", "20240101"],
                "指数・系列": ["CI 先行指数", "CI 一致指数"],
                "value": [105.0, 110.0],
            })
        return pl.DataFrame({
            "date": ["20240101", "20240101"],
            "国籍・地域": ["韓国", "米国"],
            "value": [800000.0, 200000.0],
        })

    hub.get_estat = fake_get_estat  # type: ignore[assignment]
    df_keiki = hub.get_keiki_di(series="先行指数")
    assert df_keiki.height == 1
    assert df_keiki["value"][0] == 105.0

    df_inbound = hub.get_inbound_visitors(country="韓国")
    assert df_inbound.height == 1
    assert df_inbound["value"][0] == 800000.0


def test_new_estat_presets_dispatch_correct_ids(
    hub: OpenDataHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """需要予測向け新規 e-Stat プリセット群が正しい statsDataId を呼び出す。"""
    monkeypatch.setenv("ESTAT_API_KEY", "dummy")
    called_ids: list[str] = []

    def fake_get_estat(stats_data_id, app_id=None, **kwargs):
        called_ids.append(stats_data_id)
        return pl.DataFrame({"date": ["20240101"], "value": [1.0]})

    hub.get_estat = fake_get_estat  # type: ignore[assignment]
    hub.get_retail_sales()
    hub.get_industrial_production()
    hub.get_housing_starts()
    hub.get_economy_watchers()
    hub.get_household_spending()
    hub.get_monthly_wages()

    assert called_ids == [
        "0003355268",
        "0003335036",
        "0003103532",
        "0003348423",
        "0003343671",
        "0003318162",
    ]

