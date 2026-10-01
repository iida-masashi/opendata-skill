"""data_suggester の fail-loud 回帰テスト（2026 リファクタリング G5）。"""
import subprocess
import sys
from pathlib import Path

import pytest

import data_suggester

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "data_suggester.py"


def test_missing_guide_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data_suggester.os.path, "exists", lambda _p: False)
    with pytest.raises(FileNotFoundError, match="INDUSTRY_GUIDE.md"):
        data_suggester.suggest_data("Retail")


def test_no_match_is_not_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    data_suggester.suggest_data("zzz-no-such-keyword-zzz")
    assert "No exact matches" in capsys.readouterr().out


def test_cli_missing_guide_exits_nonzero(tmp_path: Path) -> None:
    # INDUSTRY_GUIDE.md が ../references に無い場所へスクリプトを複製して実行する
    (tmp_path / "scripts").mkdir()
    copied = tmp_path / "scripts" / "data_suggester.py"
    copied.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    env_path = str(SCRIPT.parent)  # api_utils を import できるようにする
    r = subprocess.run(
        [sys.executable, str(copied), "Retail"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**__import__("os").environ, "PYTHONPATH": env_path, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode != 0
    assert "INDUSTRY_GUIDE.md" in r.stderr
