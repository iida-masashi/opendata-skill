import functools
import logging
import os
import sys
import time
import urllib.error
import urllib.request

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

def require_api_key(env_var_name: str, site_name: str, url: str) -> str:
    """
    環境変数からAPIキーを取得し、存在しない場合は親切なエラーメッセージを出力して終了するわ。
    """
    key = os.getenv(env_var_name)
    if not key:
        error_msg = (
            f"\n❌ エラー: 必須の API キー '{env_var_name}' が設定されていません。\n"
            f"💡 取得方法: {site_name} ({url}) にアクセスして API キーを取得し、\n"
            f"プロジェクトルートの `.env` ファイルに以下の形式で追記してください。\n"
            f"{env_var_name}=あなたの取得したキー\n"
        )
        print(error_msg, file=sys.stderr)
        sys.exit(1)
    return key

def rate_limited(max_calls: int, period: float):
    """
    簡単なレートリミットを実現するデコレータ。
    指定した期間 (period 秒) に最大 max_calls 回しか実行されないように Sleep を入れる。
    """
    min_interval = period / float(max_calls)

    def decorator(func):
        last_called = [0.0]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

def _is_transient(exc: BaseException) -> bool:
    """リトライすべき一時的エラーだけ True を返す。

    プログラムエラー (KeyError/ValueError 等) は即失敗させ、無駄な5回リトライと
    指数バックオフを避ける。ネットワーク系と HTTP 429/5xx のみ再試行対象。
    """
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return True
    # requests は任意依存。入っていれば 429/5xx と接続/タイムアウト例外を拾う。
    try:
        import requests

        if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True
        if isinstance(exc, requests.exceptions.HTTPError):
            resp = getattr(exc, "response", None)
            code = getattr(resp, "status_code", None)
            return code == 429 or (code is not None and 500 <= code < 600)
    except ImportError:
        pass
    return False


# ネットワークエラーや 429 Too Many Requests / 5xx でのみリトライするデコレータ。
# 各フェッチャーは自身の requests.get を呼ぶ薄い helper をこのデコレータで包んで使う
# (テストが <module>.requests.get を patch できるようにするため)。
retry_with_ratelimit = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception(_is_transient),
    reraise=True
)
