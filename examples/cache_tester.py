import shutil
import time
from pathlib import Path

from scripts.opendata_hub import OpenDataHub


def test_cache_logic() -> None:
    """Verifies the caching mechanism by timing two consecutive weather data fetches."""
    hub = OpenDataHub(cache_dir=".cache_test")

    # 1. Weather Fetch (First time - should be real fetch)
    print("--- Fetching weather (1st time) ---")
    start_time = time.time()
    df1 = hub.get_weather(lat=35.6895, lon=139.6917)
    duration1 = time.time() - start_time
    print(f"Duration 1: {duration1:.2f}s, Rows: {len(df1)}")

    # 2. Weather Fetch (Second time - should be from cache)
    print("\n--- Fetching weather (2nd time - cached) ---")
    start_time = time.time()
    df2 = hub.get_weather(lat=35.6895, lon=139.6917)
    duration2 = time.time() - start_time
    print(f"Duration 2: {duration2:.2f}s, Rows: {len(df2)}")

    assert not df1.is_empty()
    assert len(df1) == len(df2)
    assert duration2 < duration1
    print("\n✅ Caching logic verified! Second fetch was significantly faster.")

if __name__ == "__main__":
    try:
        test_cache_logic()
    finally:
        test_cache = Path(".cache_test")
        if test_cache.exists():
            shutil.rmtree(test_cache)
