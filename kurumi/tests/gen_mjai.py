"""从帧文件夹回放，生成 mjai.jsonl（不含 AI）。

用法（任意目录执行均可）：
    python tests/gen_mjai.py <frames_dir>                    # 从一局开头
    python tests/gen_mjai.py <frames_dir> --state gs.json    # 从 gamestate 起始值开始（对局中途）
    python tests/gen_mjai.py <frames_dir> -o out.jsonl       # 指定输出

默认输出到 <frames_dir 的上级目录>/mjai.jsonl，即 tests/cases/<name>/mjai.jsonl。
帧间隔固定 50ms。gs.json 是 gamestate 字典，可带 "phase"（Tsumo/Dahai/Claim ...，缺省 Tsumo）。

确定性：单线程 + 虚拟时钟。watcher 不起线程，main 每次 time.sleep 都让虚拟时间前进，
期间按 POLLING_INTERVAL 在当前帧上手动跑 watcher.step；当前帧 = frames[虚拟时间 // 50ms]。
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FRAME_MS = 50
FRAME_EXTS = ('.jpg', '.jpeg', '.png')


class ReplayFinished(Exception):
    pass


class VirtualClock:
    """整数毫秒虚拟时钟，避免浮点累加误差导致 watcher 节拍漂移。"""

    def __init__(self, files, poll_ms):
        self.files = files
        self.poll_ms = poll_ms
        self.now_ms = 0
        self.watcher = None
        self.events = None       # game.mjai（同一个 list）
        self.cut = None          # 帧耗尽时 events 的长度，之后产生的事件不计入
        self._next_watch = None
        self._cache = (None, None)

    def frame(self):
        import cv2
        import numpy as np
        idx = min(self.now_ms // FRAME_MS, len(self.files) - 1)
        if self._cache[0] != idx:
            data = np.fromfile(str(self.files[idx]), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError(f'读帧失败: {self.files[idx]}')
            self._cache = (idx, img)
        return self._cache[1]

    def _advance(self, t_ms):
        self.now_ms = max(self.now_ms, t_ms)
        if self.now_ms // FRAME_MS >= len(self.files):
            if self.cut is None:
                self.cut = len(self.events)
            raise ReplayFinished()

    def sleep(self, sec):
        target = self.now_ms + max(int(round(sec * 1000)), 0)
        w = self.watcher
        while True:
            if w._running:
                if self._next_watch is None:
                    self._next_watch = self.now_ms      # watcher 刚起，立刻跑第一轮
                nxt = self._next_watch
            else:
                self._next_watch = None
                nxt = None
            if nxt is None or nxt > target:
                break
            self._advance(nxt)
            w.manual_step()
            self._next_watch += self.poll_ms
        self._advance(target)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('frames', help='帧文件夹')
    ap.add_argument('--state', help='gamestate 起始值（JSON 文件）')
    ap.add_argument('-o', '--output', help='输出文件，默认 <frames 上级>/mjai.jsonl')
    args = ap.parse_args()

    frames_dir = Path(args.frames).resolve()
    out_path = Path(args.output).resolve() if args.output else frames_dir.parent / 'mjai.jsonl'
    state = json.loads(Path(args.state).read_text(encoding='utf-8')) if args.state else None
    files = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in FRAME_EXTS)
    if not files:
        sys.exit(f'帧目录里没有图片: {frames_dir}')

    # 代码里用 ./ref/... 相对路径，hora.py 在 import 时读模板，必须先 chdir 再 import
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    import screenshot
    from change_watcher import ChangeWatcher
    from config import POLLING_INTERVAL
    from game import Game
    from gamestate import Phase

    watcher = ChangeWatcher(manual=True)
    game = Game(use_bot=False, watcher=watcher)
    if state is not None:
        state = dict(state)
        phase = state.pop('phase', 'Tsumo')
        game.start_with_state(state)
        game.phase = Phase[str(phase).split('.')[-1]]

    clock = VirtualClock(files, int(round(POLLING_INTERVAL * 1000)))
    clock.watcher = watcher
    clock.events = game.mjai

    # 替换取帧入口：帧由虚拟时间决定，而不是 set_replay_folder 那种「每调用一次推进一张」
    t0 = time.perf_counter()
    with mock.patch('time.sleep', clock.sleep), \
            mock.patch.object(screenshot, '_read_source', clock.frame):
        try:
            game.main()
        except ReplayFinished:
            pass
        except Exception:
            traceback.print_exc()
            sys.exit('回放过程中抛出异常，未生成 mjai.jsonl')
        finally:
            watcher.stop()

    # 帧耗尽后 wait_new_kyoku 的裸 except 会吞掉 ReplayFinished 并走到 EndGame，
    # 那之后产生的事件不属于录像，按耗尽时刻截断。
    events = game.mjai if clock.cut is None else game.mjai[:clock.cut]
    if not events:
        sys.exit('没有产生任何事件，未生成 mjai.jsonl（检查帧是否正确，或 --state 的 phase 是否与画面一致）')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    print(f'已生成 {out_path}（{len(events)} 条事件；虚拟 {clock.now_ms / 1000:.0f}s，实际耗时 {time.perf_counter() - t0:.0f}s）')


if __name__ == '__main__':
    main()
