"""Hub の実際の _load_module で全フェッチャーを読み込めることを、汚れていない sys.path で検証する。

conftest は scripts/ を sys.path に入れるため、プロセス内のテストでは
「scripts/ が path に無いと相対 import が壊れる」不具合が隠れる。ここではサブプロセスで
リポジトリルートだけを path に置き、ライブラリ利用者と同じ条件で確認する。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SCRIPT = r"""
import sys
root = sys.argv[1]
sys.path = [p for p in sys.path if not p.rstrip("/\\").endswith("scripts")]
sys.path.insert(0, root)
from scripts.opendata_hub import OpenDataHub
hub = OpenDataHub(cache_dir=sys.argv[2])
failed = []
for name in sorted(hub.fetchers):
    try:
        hub._load_module(name)
    except Exception as e:
        failed.append(f"{name}: {type(e).__name__}: {e}")
# 関数内で遅延 import するフェッチャー（from api_utils import ... / from fred_fetcher import ...）も解決できること
import importlib.util
for mod in ("api_utils", "fred_fetcher"):
    if importlib.util.find_spec(mod) is None:
        failed.append(f"lazy import target not resolvable: {mod}")
print("\n".join(failed))
sys.exit(1 if failed else 0)
"""


def test_all_fetchers_load_via_hub_without_scripts_on_path(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(ROOT), str(tmp_path / "cache")],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
