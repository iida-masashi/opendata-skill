"""Tests for the narrowed retry predicate in api_utils (2026 audit, group 1d).

The old decorator retried on bare Exception, so programming errors (KeyError etc.)
were retried 5x with ~16s of dead backoff. The fix retries ONLY transient errors
(network + HTTP 429/5xx).
"""
from unittest.mock import patch

import pytest
import requests


from api_utils import _is_transient, retry_with_ratelimit


def _http_error(status: int) -> requests.exceptions.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


def test_is_transient_classification() -> None:
    # transient
    assert _is_transient(ConnectionError())
    assert _is_transient(TimeoutError())
    assert _is_transient(requests.exceptions.Timeout())
    assert _is_transient(_http_error(429))
    assert _is_transient(_http_error(503))
    # NOT transient
    assert not _is_transient(KeyError("GET_STATS_DATA"))
    assert not _is_transient(ValueError("bad"))
    assert not _is_transient(_http_error(404))
    assert not _is_transient(_http_error(400))


def test_programming_error_fails_fast() -> None:
    """KeyError は再試行されず 1 回で送出される（無駄な5回バックオフを避ける）。"""
    calls = {"n": 0}

    @retry_with_ratelimit
    def boom() -> None:
        calls["n"] += 1
        raise KeyError("GET_STATS_DATA")

    with pytest.raises(KeyError):
        boom()
    assert calls["n"] == 1  # was 5 before the fix


def test_429_is_retried() -> None:
    """HTTP 429 は最大5回まで再試行される。"""
    calls = {"n": 0}

    @retry_with_ratelimit
    def rate_limited_call() -> None:
        calls["n"] += 1
        raise _http_error(429)

    with pytest.raises(requests.exceptions.HTTPError):
        rate_limited_call()
    assert calls["n"] == 5


@patch("meteo_fetcher.requests.get")
def test_module_get_helper_retries_on_5xx_then_succeeds(mock_get) -> None:
    """各フェッチャーの _get_with_retry が 5xx で再試行し、回復したら結果を返す。

    meteo_fetcher を代表例として使う（全 REST フェッチャー共通のパターン）。
    """
    import meteo_fetcher

    class _Resp:
        def __init__(self, code: int) -> None:
            self.status_code = code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise _http_error(self.status_code)

    # 503, 503, 200 の順で返す
    mock_get.side_effect = [_Resp(503), _Resp(503), _Resp(200)]

    resp = meteo_fetcher._get_with_retry("https://example.test")
    assert resp.status_code == 200
    assert mock_get.call_count == 3
