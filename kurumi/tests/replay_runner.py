"""回放回归测试：用录好的帧重放整局，把生成的 mjai 事件流和期望的 jsonl 比对。

目录结构（放在项目根目录下的 tests/）：
    tests/
      replay_runner.py
      test_replay.py              # pytest 入口（可选）
      cases/
        <case_name>/
          frames/                 # 按文件名排序的帧（.jpg/.png），如 video_to_frames.py 的输出
          mjai.jsonl              # 期望的 mjai 事件流，一行一个事件
          state.json              # 可选：从对局中途开始，见下
          meta.json               # 可选：
                                  #   frame_ms     帧间隔毫秒，缺省 100
                                  #   frames       帧目录（相对用例目录），缺省 "frames"；
                                  #                多个用例可共用一份长录像
                                  #   start_frame / end_frame   切片 [start, end)，按排序后的序号
      out/<case_name>/actual.jsonl   # 每次运行的实际输出（失败时对照用）

用法（在任意目录执行均可，内部会 chdir 到项目根）：
    python tests/replay_runner.py                  # 跑全部用例
    python tests/replay_runner.py case_a case_b    # 跑指定用例
    python tests/replay_runner.py case_a --update  # 用当前输出覆盖期望（人工确认后再提交）

中途开始（state.json）：
    不提供则从一局开头完整重放（wait_new_kyoku → start_kyoku …）。
    提供则跳过开局，直接用 gamestate 快照初始化后进入指定 phase，期望的 mjai.jsonl
    只包含「从该时刻起」产生的事件（不含 start_kyoku）。格式 = gamestate 字典 + 两个可选键：
        "phase": "Tsumo" | "Dahai" | "Claim" ...（Phase 枚举名或数值，缺省 Tsumo）
        "_game": {"riichi_to_accepted": 2, "need_open_dora": true}   # Game 上不在 gamestate 里的状态
    帧序列的第 0 帧 = 快照对应的时刻。phase 要和画面一致：
        Tsumo  快照时轮到 current_player 摸牌（自己时需要能看到摸牌）
        Dahai  current_player 已摸牌、等待打牌
        Claim  刚打出牌（需要 last_player / last_dahai），等待别家鸣牌或下家行动

确定性：
    回放时 main / watcher 若各开线程抢同一个帧游标，结果取决于线程调度，不可复现。
    这里改为单线程 + 虚拟时钟：
      - ChangeWatcher(manual=True)，不起线程；
      - patch time.sleep：main 每次 sleep 都让虚拟时间前进，期间按 POLLING_INTERVAL
        的节奏在「当前帧」上手动跑 watcher.step；
      - 帧 = frames[虚拟时间 // frame_ms]，main 和 watcher 读到的都是当前时刻的帧；
      - 不加载 Bot，只比较 mjai 事件。
    每个用例在独立子进程里跑，避免模块级 stable_func 等单例状态在用例之间串扰。
"""
import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES_DIR = HERE / 'cases'
OUT_DIR = HERE / 'out'
DEFAULT_FRAME_MS = 100
FRAME_EXTS = ('.jpg', '.jpeg', '.png')


# ------------------------------------------------------------------ 工具
def load_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def dump_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')


def _norm(e):
    return json.dumps(e, sort_keys=True, ensure_ascii=False)


def compare(expected, actual):
    exp = [_norm(e) for e in expected]
    act = [_norm(e) for e in actual]
    if exp == act:
        return True
    n = min(len(exp), len(act))
    first = next((i for i in range(n) if exp[i] != act[i]), n)
    print(f'  事件数 期望 {len(exp)} / 实际 {len(act)}，首个差异在第 {first} 条（从 0 计）')
    for i in range(max(0, first - 3), first):
        print(f'    {i}  {exp[i]}')
    print(f'  期望[{first}] {exp[first] if first < len(exp) else "<无>"}')
    print(f'  实际[{first}] {act[first] if first < len(act) else "<无>"}')
    return False


# ------------------------------------------------------------------ 虚拟时钟
class ReplayFinished(Exception):
    pass


class VirtualClock:
    """整数毫秒的虚拟时钟，避免浮点累加误差导致 watcher 节拍漂移。"""

    def __init__(self, files, frame_ms, poll_ms):
        self.files = files
        self.frame_ms = frame_ms
        self.poll_ms = poll_ms
        self.now_ms = 0
        self.watcher = None
        self.events = None          # game.mjai（同一个 list 对象）
        self.cut = None             # 帧耗尽时 events 的长度，之后产生的事件不计入
        self._next_watch = None
        self._cache = (None, None)

    def frame(self):
        import cv2
        import numpy as np
        idx = min(self.now_ms // self.frame_ms, len(self.files) - 1)
        if self._cache[0] != idx:
            data = np.fromfile(str(self.files[idx]), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError(f'读帧失败: {self.files[idx]}')
            self._cache = (idx, img)
        return self._cache[1]

    def _advance(self, t_ms):
        self.now_ms = max(self.now_ms, t_ms)
        if self.now_ms // self.frame_ms >= len(self.files):
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


# ------------------------------------------------------------------ 中途开始
def parse_phase(v):
    from gamestate import Phase
    if isinstance(v, int):
        return Phase(v)
    return Phase[str(v).split('.')[-1]]     # 兼容 "Dahai" / "Phase.Dahai"


def init_from_state(game, snap):
    """用 gamestate 快照初始化 Game，跳过开局识别。"""
    snap = dict(snap)
    phase = parse_phase(snap.pop('phase', 'Tsumo'))
    game_attrs = snap.pop('_game', {})
    game.start_with_state(snap)             # set_gamestate + watcher.reset/start
    game.phase = phase
    for k, v in game_attrs.items():
        setattr(game, k, v)


# ------------------------------------------------------------------ 单个用例
def run_case(case_dir, update=False):
    case_dir = Path(case_dir).resolve()
    name = case_dir.name
    frames_dir = case_dir / 'frames'
    expected_path = case_dir / 'mjai.jsonl'

    meta = {}
    if (case_dir / 'meta.json').exists():
        meta = json.loads((case_dir / 'meta.json').read_text(encoding='utf-8'))
    frame_ms = int(meta.get('frame_ms', DEFAULT_FRAME_MS))
    if 'frames' in meta:
        frames_dir = (case_dir / meta['frames']).resolve()

    files = sorted(p for p in frames_dir.iterdir() if p.suffix.lower() in FRAME_EXTS)
    files = files[int(meta.get('start_frame', 0)):(meta.get('end_frame') or None)]
    if not files:
        print(f'[{name}] FAIL  frames 目录为空: {frames_dir}')
        return False

    # 代码里大量使用 ./ref/... 相对路径，且 hora.py 在 import 时读模板，必须先 chdir
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    import screenshot
    from change_watcher import ChangeWatcher
    from config import POLLING_INTERVAL
    from game import Game

    watcher = ChangeWatcher(manual=True)
    game = Game(use_bot=False, watcher=watcher)
    state_path = case_dir / 'state.json'
    if state_path.exists():
        init_from_state(game, json.loads(state_path.read_text(encoding='utf-8')))
    clock = VirtualClock(files, frame_ms, int(round(POLLING_INTERVAL * 1000)))
    clock.watcher = watcher
    clock.events = game.mjai

    error = None
    # 帧由虚拟时间决定，替换取帧入口（与 gen_mjai.py 同一做法；
    # 本分支的 screenshot 没有 set_frame_provider，只有 _read_source）
    with mock.patch('time.sleep', clock.sleep), \
            mock.patch.object(screenshot, '_read_source', clock.frame):
        try:
            game.main()
        except ReplayFinished:
            pass
        except Exception:
            error = traceback.format_exc()
        finally:
            watcher.stop()

    # 帧耗尽后 wait_new_kyoku 的裸 except 会吞掉 ReplayFinished 并走到 EndGame，
    # 那之后产生的事件不是真实对局的一部分，按耗尽时刻截断。
    actual = list(game.mjai if clock.cut is None else game.mjai[:clock.cut])

    actual_path = OUT_DIR / name / 'actual.jsonl'
    dump_jsonl(actual_path, actual)

    if error:
        print(f'[{name}] FAIL  对局中抛出异常（已产出 {len(actual)} 条事件）:\n{error}')
        return False

    if update:
        dump_jsonl(expected_path, actual)
        print(f'[{name}] UPDATED  写入 {len(actual)} 条事件 -> {expected_path}')
        return True

    if not expected_path.exists():
        print(f'[{name}] FAIL  缺少期望文件 {expected_path}（首次请加 --update 生成并人工确认）')
        return False

    if compare(load_jsonl(expected_path), actual):
        print(f'[{name}] PASS  {len(actual)} 条事件一致')
        return True

    print(f'[{name}] FAIL  实际输出见 {actual_path}')
    return False


# ------------------------------------------------------------------ CLI
def list_cases():
    if not CASES_DIR.is_dir():
        return []
    return sorted(p for p in CASES_DIR.iterdir()
                  if (p / 'frames').is_dir() or (p / 'meta.json').exists())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cases', nargs='*', help='用例名（tests/cases 下的目录名），缺省跑全部')
    ap.add_argument('--update', action='store_true', help='用当前输出覆盖期望 mjai.jsonl')
    ap.add_argument('--run-one', help=argparse.SUPPRESS)   # 子进程入口：用例目录
    args = ap.parse_args()

    if args.run_one:
        sys.exit(0 if run_case(args.run_one, update=args.update) else 1)

    cases = list_cases()
    if args.cases:
        names = set(args.cases)
        missing = names - {c.name for c in cases}
        if missing:
            print(f'找不到用例: {sorted(missing)}')
            sys.exit(2)
        cases = [c for c in cases if c.name in names]
    if not cases:
        print(f'没有用例（{CASES_DIR}）')
        sys.exit(2)

    failed = []
    for c in cases:
        cmd = [sys.executable, str(Path(__file__).resolve()), '--run-one', str(c)]
        if args.update:
            cmd.append('--update')
        if subprocess.run(cmd).returncode != 0:
            failed.append(c.name)

    print(f'\n共 {len(cases)} 个用例，失败 {len(failed)} 个' + (f': {failed}' if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
