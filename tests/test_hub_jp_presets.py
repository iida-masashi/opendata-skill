"""Tests for the e-Stat-backed JP preset hub methods (Phase 2 ⑧ + ⑪).

These wrap the existing e-Stat fetch path with verified statsDataIds:
  - get_keiki_di():        景気動向指数 (CI/DI, incl. 先行指数)  -> 0003446461
  - get_inbound_visitors(): 訪日外客数 (港別 入国外国人国籍・地域) -> 0003449064
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.opendata_hub import OpenDataHub  # noqa: E402


@pytest.fixture
def hub(tmp_path: Path) -> OpenDataHub:
    return OpenDataHub(cache_dir=str(tmp_path / "cache"))


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
            pl.DataFrame({"date": ["202601"], "value": [17.0]}).write_csv(output_file)
            return pl.DataFrame({"date": ["202601"], "value": [17.0]})

    hub.fetchers["boj"] = Path("boj_fetcher.py")
    hub._load_module = lambda n, _m=_FakeMod(): _m  # type: ignore[assignment]

    df = hub.get_boj_tankan(series="tankan_large_mfg")
    assert captured.get("series") == "tankan_large_mfg"
    assert not df.is_empty()
