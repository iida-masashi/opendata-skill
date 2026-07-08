"""Tests for OpenDataHub.get_many parallel fan-out (Phase 2 ⑥)."""
import sys
import threading
import time
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.opendata_hub import OpenDataHub  # noqa: E402


@pytest.fixture
def hub(tmp_path: Path) -> OpenDataHub:
    return OpenDataHub(cache_dir=str(tmp_path / "cache"))


def test_get_many_returns_dict_keyed_by_label(hub: OpenDataHub) -> None:
    hub.get_weather = lambda **kw: pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})  # type: ignore[assignment]
    hub.get_fred = lambda **kw: pl.DataFrame({"date": ["2024-01-01"], "value": [2.0]})  # type: ignore[assignment]

    out = hub.get_many(
        [
            {"label": "w", "method": "get_weather", "kwargs": {"lat": 35.0, "lon": 139.0}},
            {"label": "f", "method": "get_fred", "kwargs": {"series_id": "UNRATE"}},
        ]
    )
    assert set(out.keys()) == {"w", "f"}
    assert out["w"]["value"][0] == 1.0
    assert out["f"]["value"][0] == 2.0


def test_get_many_runs_concurrently(hub: OpenDataHub) -> None:
    """3 calls that each sleep ~0.3s should finish well under the serial 0.9s."""
    barrier_hits = []

    def slow(**kw):
        barrier_hits.append(threading.current_thread().name)
        time.sleep(0.3)
        return pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})

    hub.get_weather = slow  # type: ignore[assignment]

    specs = [
        {"label": f"s{i}", "method": "get_weather", "kwargs": {"lat": i, "lon": i}}
        for i in range(3)
    ]
    start = time.monotonic()
    out = hub.get_many(specs, max_workers=3)
    elapsed = time.monotonic() - start

    assert len(out) == 3
    assert elapsed < 0.8  # serial would be ~0.9s
    assert len(set(barrier_hits)) > 1  # actually ran on multiple threads


def test_get_many_concurrent_none_returners_no_temp_race(hub: OpenDataHub) -> None:
    """Two concurrent get_weather calls must NOT race on a shared temp CSV.

    meteo writes a fixed temp file (None-returner -> CSV fallback path). If the
    temp path isn't unique per call, one caller gets the other's data and one
    gets silently-empty. Mock only meteo.requests.get so the real get_weather ->
    _fetch_to_df -> CSV roundtrip executes."""
    import meteo_fetcher

    def fake_get(url, params=None, **kwargs):
        lat = float(params["latitude"])
        # distinct, slow-ish payload per coordinate to force overlap
        import time as _t

        _t.sleep(0.15)

        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                # Open-Meteo-ish hourly payload (default hourly=True)
                return {
                    "hourly": {
                        "time": ["2024-01-01T00:00", "2024-01-01T01:00"],
                        "temperature_2m": [lat, lat + 1],
                    }
                }

        return _R()

    import unittest.mock as um

    with um.patch.object(meteo_fetcher.requests, "get", side_effect=fake_get):
        out = hub.get_many(
            [
                {"label": "tokyo", "method": "get_weather", "kwargs": {"lat": 35.0, "lon": 139.0}},
                {"label": "osaka", "method": "get_weather", "kwargs": {"lat": 34.0, "lon": 135.0}},
            ],
            max_workers=2,
        )

    assert not out["tokyo"].is_empty(), "tokyo lost its data to a temp-file race"
    assert not out["osaka"].is_empty(), "osaka lost its data to a temp-file race"
    # The two must carry DIFFERENT data (no cross-contamination)
    assert not out["tokyo"].equals(out["osaka"])


def test_get_many_isolates_failures(hub: OpenDataHub) -> None:
    """One failing fetch must not sink the others; failed label maps to empty df."""
    hub.get_weather = lambda **kw: pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})  # type: ignore[assignment]

    def boom(**kw):
        raise RuntimeError("api down")

    hub.get_fred = boom  # type: ignore[assignment]

    out = hub.get_many(
        [
            {"label": "ok", "method": "get_weather", "kwargs": {"lat": 1, "lon": 1}},
            {"label": "bad", "method": "get_fred", "kwargs": {"series_id": "X"}},
        ]
    )
    assert not out["ok"].is_empty()
    assert out["bad"].is_empty()  # failure isolated, not raised
