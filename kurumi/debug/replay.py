"""确定性重放：读 recorder.dump 出来的现场目录，用【同一份】ChangeWatcher.step
在录下的无损帧 + 当时的 gamestate 上重跑，逐帧比对识别输出。

    python replay.py logs/dump/20260710_153000_stall_Dahai
    python replay.py <dir> --from 1200 --to 1300 -v
    pytest 里：assert not replay(folder)

输出不一致 = 识别不确定/受状态竞态影响（标了 gs_changed 的帧尤其可疑）；
全部一致而 live 出过错 = 问题在 main 的消费/状态机侧，去看 events.jsonl 的 main 事件。
"""
import argparse
import bisect
import copy
import json
import os
import queue
import sys

# 本文件在 kurumi/debug/ 下。项目里 game.py 等用的是顶层导入（from screenshot import ...），
# 同时 recorder 用包路径 kurumi.debug.recorder，所以两个目录都要在 sys.path 里：
#   kurumi/ 目录      → screenshot、change_watcher、gamestate ...
#   kurumi 的上一级   → kurumi.debug.recorder
# 并且 change_watcher 一律按顶层名导入，与 game.py 保持同一个模块身份，避免重复加载。
_KURUMI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.dirname(_KURUMI_DIR), _KURUMI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2

from kurumi.debug import recorder
from kurumi.debug.recorder import Recorder, dumps


def _jl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def replay(folder, start=None, end=None, warmup=5, verbose=False):
    """返回不一致列表 [{'fid','expected','got','gs_changed'}]。前 warmup 帧只用来预热
    stable_func 的内部采样，不计入不一致。"""
    with open(os.path.join(folder, 'meta.json'), encoding='utf-8') as f:
        meta = json.load(f)
    frames = {e['fid']: e for e in _jl(os.path.join(folder, 'frames.jsonl'))}
    events = _jl(os.path.join(folder, 'events.jsonl'))
    states = _jl(os.path.join(folder, 'states.jsonl'))
    state_fids = [s['fid'] for s in states]

    print(f'[meta] reason={meta.get("reason")} dropped_frames={meta.get("dropped_frames")}')

    steps = [e for e in events if e['src'] == 'watcher' and e['kind'] == 'step'
             and frames.get(e['fid'], {}).get('file')
             and (start is None or e['fid'] >= start) and (end is None or e['fid'] <= end)]
    steps.sort(key=lambda e: frames[e['fid']]['seq'])
    if not steps:
        raise SystemExit('没有可重放的 watcher step')

    # 用独立 recorder（不落盘不存帧），避免重放污染现场；必须在构造 ChangeWatcher 之前设置
    recorder.set_recorder(Recorder(persist=False, store_frames=False))
    from change_watcher import ChangeWatcher
    from gamestate import set_gamestate
    w = ChangeWatcher()

    def state_at(fid):
        i = bisect.bisect_right(state_fids, fid) - 1
        return states[max(i, 0)]['state']

    # 初始私有状态 + 队列内容取自窗口起点的快照
    first = steps[0]
    ex = state_at(first['fid']).get('extra', {}).get('watcher', {})
    w._current_player = ex.get('current_player')
    w._player_to_id = ex.get('player_to_id')
    for name, items in ex.get('queues', {}).items():
        for it in items:
            getattr(w, name).put(it)

    # 控制事件：watcher.reset 与 main 对队列的 consume，按 seq 在每帧之前施加
    first_seq = frames[first['fid']]['seq']
    ctl = sorted((e for e in events if e['seq'] > first_seq and
                  ((e['src'] == 'watcher' and e['kind'] == 'reset') or
                   (e['src'] == 'main' and e['kind'] == 'consume'))), key=lambda e: e['seq'])
    ci = 0

    diffs = []
    for i, ev in enumerate(steps):
        fr = frames[ev['fid']]
        while ci < len(ctl) and ctl[ci]['seq'] < fr['seq']:
            c = ctl[ci]
            ci += 1
            if c['kind'] == 'reset':
                w.reset(c['current_player'], c['player_to_id'])
            else:
                try:
                    getattr(w, c['q']).get_nowait()
                except queue.Empty:
                    pass

        img = cv2.imread(os.path.join(folder, 'frames', fr['file']), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f'读帧失败: {fr["file"]}')
        set_gamestate(copy.deepcopy(state_at(ev['fid'])['gs']))

        got = json.loads(dumps(w.step(img, ev['fid'])))
        exp = ev['out']
        ok = got == exp
        if verbose:
            print(f'fid={ev["fid"]:6d} {"OK " if ok else "DIFF"} {got if ok else (exp, got)}')
        if not ok and i >= warmup:
            diffs.append({'fid': ev['fid'], 'expected': exp, 'got': got,
                          'gs_changed': bool(ev.get('gs_changed'))})

    print(f'[replay] {len(steps)} 帧, 不一致 {len(diffs)} 帧')
    for d in diffs[:20]:
        flag = '  (live 该帧 step 期间 gamestate 被改动 → 疑似线程竞态)' if d['gs_changed'] else ''
        print(f'  fid={d["fid"]}\n    live  : {d["expected"]}\n    replay: {d["got"]}{flag}')
    return diffs


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--from', dest='start', type=int)
    ap.add_argument('--to', dest='end', type=int)
    ap.add_argument('--warmup', type=int, default=5)
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    folder = os.path.abspath(a.folder)     # 先按当前目录解析，再切换工作目录
    os.chdir(_KURUMI_DIR)                  # hora/tile 等用 ./ref/... 相对路径加载模板和模型
    sys.exit(1 if replay(folder, a.start, a.end, a.warmup, a.verbose) else 0)
