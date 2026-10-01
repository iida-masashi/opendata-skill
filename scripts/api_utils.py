import functools
import logging
import os
import sys
import threading
import time
import urllib.error
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60


class MissingApiKeyError(RuntimeError):
    """必須の API キーが環境変数に設定されていない。"""


def require_api_key(env_var_name: str, site_name: str, url: str) -> str:
    """環境変数から API キーを取得する。未設定なら取得方法を添えて MissingApiKeyError を送出する。

    ライブラリ経路（Hub / get_many）から呼ばれるため sys.exit はしない。
    CLI の終了コードへの変換は cli_entry が行う。
    """
    key = os.getenv(env_var_name)
    if not key:
        raise MissingApiKeyError(
            f"必須の API キー '{env_var_name}' が設定されていません。\n"
            f"💡 取得方法: {site_name} ({url}) にアクセスして API キーを取得し、\n"
            f"プロジェクトルートの `.env` ファイルに以下の形式で追記してください。\n"
            f"{env_var_name}=あなたの取得したキー"
        )
    return key


def cli_entry(main: Callable[[], object]) -> None:
    """CLI の main() を実行し、例外を stderr への表示と終了コード 1 に変換する。"""
    try:
        main()
    except Exception as e:  # noqa: BLE001 - CLI 境界で終了コードに変換する
        print(f"\n❌ {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def rate_limited(max_calls: int, period: float):
    """
    簡単なレートリミットを実現するデコレータ。
    指定した期間 (period 秒) に最大 max_calls 回しか実行されないように、呼び出し開始の間隔を空ける。
    スレッド間で共有され、実行枠は呼び出し前にロック下で確保する（get_many の並列実行でも有効）。
    """
    min_interval = period / float(max_calls)

    def decorator(func):
        lock = threading.Lock()
        next_slot = [0.0]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                now = time.monotonic()
                wait = next_slot[0] - now
                next_slot[0] = max(now, next_slot[0]) + min_interval
            if wait > 0:
                time.sleep(wait)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def _is_transient(exc: BaseException) -> bool:
    """リトライすべき一時的エラーだけ True を返す。

    プログラムエラー (KeyError/ValueError 等) は即失敗させ、無駄な5回リトライと
    指数バックオフを避ける。ネットワーク系と HTTP 429/5xx のみ再試行対象。
    """
    # urllib.error.HTTPError は URLError のサブクラスなので先に status で判定する。
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
        return code == 429 or (code is not None and 500 <= code < 600)
    return False


def _backoff_sleep(seconds: float) -> None:
    """リトライ間の待機。テストはこの関数を差し替えてバックオフ待ちを省く（tests/conftest.py）。"""
    time.sleep(seconds)


# ネットワークエラーや 429 Too Many Requests / 5xx でのみリトライするデコレータ。
retry_with_ratelimit = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception(_is_transient),
    sleep=lambda seconds: _backoff_sleep(seconds),  # 呼び出し時に解決し、差し替え可能にする
    reraise=True
)


@retry_with_ratelimit
def get_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """requests.get を呼び、raise_for_status する。429/5xx・接続系エラーのみ再試行する。

    `requests.get` を呼び出し時に解決するので、テストの
    `@patch("<module>.requests.get")`（= requests モジュール自体の get を差し替える）がそのまま効く。
    """
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp


@retry_with_ratelimit
def post_with_retry(url: str, **kwargs: Any) -> requests.Response:
    """requests.post 版の get_with_retry。"""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    resp = requests.post(url, **kwargs)
    resp.raise_for_status()
    return resp


def redact(text: str, secrets: Iterable[str | None] = ()) -> str:
    """文字列中の秘密情報（URL に埋め込まれた API キー等）を伏せる。"""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def format_http_error(exc: requests.exceptions.HTTPError, secrets: Iterable[str | None] = ()) -> str:
    """HTTPError を「ステータス + API のエラー本文」の1行にする。

    `Response.__bool__` は 4xx/5xx で False になるため、`if e.response` ではなく `is not None` で判定する。
    """
    resp = exc.response
    if resp is not None:
        msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
    else:
        msg = str(exc)
    return redact(msg, secrets)


def get_with_retry_redacted(url: str, secrets: Iterable[str | None], **kwargs: Any) -> requests.Response:
    """get_with_retry を呼び、送出する例外のメッセージから秘密情報（URL に入る API キー等）を伏せる。

    HTTPError は API のエラー本文付きのメッセージにし、元の response を保持する。
    """
    secrets = list(secrets)
    try:
        return get_with_retry(url, **kwargs)
    except requests.exceptions.HTTPError as e:
        raise requests.exceptions.HTTPError(format_http_error(e, secrets), response=e.response) from None
    except requests.exceptions.RequestException as e:
        raise type(e)(redact(str(e), secrets)) from None


def default_date_range(
    start_date: str | None, end_date: str | None, days: int, fmt: str = "%Y-%m-%d"
) -> tuple[str, str]:
    """未指定の start/end を「今日(UTC) から days 日前〜今日」で補う。"""
    now = datetime.now(UTC)
    if not end_date:
        end_date = now.strftime(fmt)
    if not start_date:
        start_date = (now - timedelta(days=days)).strftime(fmt)
    return start_date, end_date


def save_output(df: pl.DataFrame, output_file: str | None) -> None:
    """output_file が指定されていれば CSV に保存する（空DFは書かない）。"""
    if not output_file or df.is_empty():
        return
    path = Path(output_file)
    if path.parent != Path():
        path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(path)
    print(f"Saved {df.height} rows to {path}")
