"""pytest：tests/cases/<name>/{frames/, mjai.jsonl, state.json?}，
用 gen_mjai.py 重放生成，与期望的 mjai.jsonl 比对。每个用例一个子进程，状态互不串扰。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CASES = (sorted(p for p in (HERE / 'cases').iterdir()
                if (p / 'frames').is_dir() and (p / 'mjai.jsonl').exists())
         if (HERE / 'cases').is_dir() else [])


def load(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.mark.parametrize('case', CASES, ids=lambda p: p.name)
def test_replay(case, tmp_path):
    out = tmp_path / 'actual.jsonl'
    cmd = [sys.executable, str(HERE / 'gen_mjai.py'), str(case / 'frames'), '-o', str(out)]
    if (case / 'state.json').exists():
        cmd += ['--state', str(case / 'state.json')]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-4000:]
    assert load(out) == load(case / 'mjai.jsonl')
