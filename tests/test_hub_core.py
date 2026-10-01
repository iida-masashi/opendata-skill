"""Hub 中核の不具合の回帰テスト（sys.exit / モジュール再実行 / レート制限 / キャッシュ並列 / 失敗の可視化）。"""
import json
import threading
import time
import urllib.error
from pathlib import Path

import polars as pl
import pytest

import api_utils
from api_utils import MissingApiKeyError, _is_transient, rate_limited, require_api_key
from scripts.cache_manager import CacheManager
from scripts.opendata_hub import OpenDataHub


def test_require_api_key_raises_instead_of_exiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_MISSING_KEY", raising=False)
    with pytest.raises(MissingApiKeyError) as ei:
        require_api_key("SOME_MISSING_KEY", "Example", "https://example.test")
    assert "SOME_MISSING_KEY" in str(ei.value)
    assert not isinstance(ei.value, SystemExit)


def test_get_many_isolates_missing_api_key(hub: OpenDataHub, monkeypatch: pytest.MonkeyPatch) -> None:
    """キー未設定の1ソースがバッチ全体（とプロセス）を落とさない。"""
    monkeypatch.setenv("ESTAT_API_KEY", "")
    hub.get_weather = lambda **kw: pl.DataFrame({"date": ["2024-01-01"], "value": [1.0]})  # type: ignore[assignment]
    out = hub.get_many([
        {"label": "estat", "method": "get_estat", "kwargs": {"stats_data_id": "0000000000"}},
        {"label": "w", "method": "get_weather", "kwargs": {"lat": 35.0, "lon": 139.0}},
    ])
    assert out["w"].height == 1
    assert out["estat"].is_empty()
    assert isinstance(hub.last_errors["estat"], MissingApiKeyError)
    assert "w" not in hub.last_errors


def test_get_many_errors_reset_per_call(hub: OpenDataHub) -> None:
    def boom(**kw: object) -> pl.DataFrame:
        raise RuntimeError("down")

    hub.get_weather = boom  # type: ignore[assignment]
    hub.get_many([{"label": "w", "method": "get_weather", "kwargs": {}}])
    assert "w" in hub.last_errors
    hub.get_weather = lambda **kw: pl.DataFrame({"value": [1.0]})  # type: ignore[assignment]
    hub.get_many([{"label": "w", "method": "get_weather", "kwargs": {}}])
    assert hub.last_errors == {}


def test_load_module_is_cached(hub: OpenDataHub) -> None:
    """毎回 exec_module するとモジュール状態（レート制限の時刻など）がリセットされる。"""
    a = hub._load_module("estat")
    b = hub._load_module("estat")
    assert a is b


def test_rate_limited_is_thread_safe() -> None:
    starts: list[float] = []
    lock = threading.Lock()

    @rate_limited(max_calls=1, period=0.2)
    def f() -> None:
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=f) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    starts.sort()
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert len(gaps) == 3
    assert min(gaps) >= 0.18, gaps


def test_urllib_http_4xx_is_not_transient() -> None:
    err404 = urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)  # type: ignore[arg-type]
    err503 = urllib.error.HTTPError("https://x", 503, "Unavailable", {}, None)  # type: ignore[arg-type]
    assert _is_transient(err404) is False
    assert _is_transient(err503) is True
    assert _is_transient(urllib.error.URLError("dns")) is True


def test_cache_concurrent_sets_keep_metadata_valid(tmp_path: Path) -> None:
    cm = CacheManager(cache_dir=str(tmp_path / "c"))
    df = pl.DataFrame({"value": [1.0, 2.0]})
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for j in range(10):
                cm.set("src", {"i": i, "j": j}, df, ttl_hours=1)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    meta = json.loads((tmp_path / "c" / "cache_metadata.json").read_text(encoding="utf-8"))
    assert len(meta) == 80
    reloaded = CacheManager(cache_dir=str(tmp_path / "c"))
    assert reloaded.get("src", {"i": 3, "j": 7}) is not None


def test_cli_entry_converts_exception_to_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    def main() -> None:
        raise MissingApiKeyError("no key")

    with pytest.raises(SystemExit) as ei:
        api_utils.cli_entry(main)
    assert ei.value.code == 1
    assert "no key" in capsys.readouterr().err


def test_missing_api_key_error_importable_from_hub() -> None:
    """ライブラリ利用者は Hub から import した例外でフェッチャーの送出を捕捉できる。"""
    from scripts.opendata_hub import MissingApiKeyError as FromHub

    assert FromHub is MissingApiKeyError
