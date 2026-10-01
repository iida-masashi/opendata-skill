"""テスト共通設定。

- scripts/ とリポジトリルートを import パスに入れる（各テストファイルでの sys.path 操作を不要にする）。
  ※ Hub の import 経路そのものは tests/test_hub_import_isolation.py がサブプロセスで検証する。
- integration マーカーの付いていないテストはネットワーク接続を禁止する。
"""
import json as _json
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from scripts.opendata_hub import OpenDataHub  # noqa: E402


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("integration"):
        return

    def _guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("非 integration テストでネットワーク接続が発生しました")

    monkeypatch.setattr(socket.socket, "connect", _guard)


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """retry_with_ratelimit のバックオフ待ちを省く（リトライ回数の検証はそのまま行える）。"""
    import api_utils

    monkeypatch.setattr(api_utils, "_backoff_sleep", lambda seconds: None)


@pytest.fixture
def hub(tmp_path: Path) -> OpenDataHub:
    return OpenDataHub(cache_dir=str(tmp_path / "cache"))


@pytest.fixture
def make_response() -> Callable[..., requests.Response]:
    """本物の requests.Response を組み立てる（raise_for_status / bool() / .json() が実物どおりに動く）。"""

    def _make(
        json: Any = None,
        text: str | None = None,
        status: int = 200,
        content: bytes | None = None,
        url: str = "https://example.test/api",
    ) -> requests.Response:
        resp = requests.Response()
        resp.status_code = status
        resp.url = url
        resp.encoding = "utf-8"
        if content is not None:
            resp._content = content
        elif json is not None:
            resp._content = _json.dumps(json).encode()
        else:
            resp._content = (text or "").encode()
        return resp

    return _make
