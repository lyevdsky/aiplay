"""飞行记录仪：让 bug 现场可以被完整、无损地复现。

运行期间【全部在内存里】，不写任何文件、不丢任何一帧：
  1. 帧   ：最近 keep_frames 帧（默认 200）的原始像素数组（不压缩、不缩放、不去重）。
  2. 事件 ：watcher 每帧的识别结果(step)、队列 put、main 的 consume/phase/mjai 等。
  3. 状态 ：每个 watcher step 开头的 gamestate + 各模块私有状态（仅变化时存）。
三者共用一个全局单调递增的 seq（线程间的全序）。

只在 异常 / F1 / POST /game/save 时 dump()：此时才把内存里的帧编码成无损 PNG 写盘，
得到 logs/dump/<时间>_<原因>/，replay.py 读它做确定性重放。

内存估算：每帧 = 宽×高×3 字节（2560×1440 ≈ 11MB），200 帧约 2.2GB。
按机器内存调 keep_frames。
"""
import json
import os
import re
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import Enum

import cv2
import numpy as np

# PNG 压缩级别只影响速度/体积，解码后与原数组逐像素一致（无损）
PNG_PARAMS = [cv2.IMWRITE_PNG_COMPRESSION, 1]


def _jsonable(o):
    if isinstance(o, Enum):
        return o.name
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=repr)
    return repr(o)


def dumps(o):
    """按 key 排序：用于状态快照（需要确定性字符串以判断「是否变化」）和重放比对。"""
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=_jsonable)


def dumps_ordered(o):
    """保持 dict 插入顺序：用于事件日志/帧索引，字段顺序固定、便于人眼阅读。"""
    return json.dumps(o, ensure_ascii=False, default=_jsonable)


class Recorder:
    def __init__(self, keep_frames=200, event_maxlen=300_000, store_frames=True):
        self.keep_frames = keep_frames
        self.store_frames = store_frames     # False：只发 fid，不存帧（replay 用）

        self._lock = threading.RLock()
        self._dump_lock = threading.Lock()
        self._tl = threading.local()
        self._seq = 0
        self._fid = 0

        self._frames = deque()               # 条目 dict（含 'arr'），按到达顺序
        self._events = deque(maxlen=event_maxlen)   # (seq, json_line)
        self._snaps = deque()                # (fid, combined_state_json)
        self._last_state = None
        self._extra = {}                     # name -> callable，返回需随快照保存的私有状态
        self._last_dump = None               # (t, path)
        self._exc_text = None                # 最近一次 log_exception 的完整文本

    def reset(self):
        """清空帧 / 事件 / 状态快照，每局开始时调用，使 recorder 每次只记录一局。
        fid / seq 计数器保持单调递增不重置，这样日志里的编号在整个进程内唯一。
        extra 回调（watcher / game 的私有状态）注册关系保留。"""
        with self._lock:
            self._frames.clear()      # 释放内存里的帧
            self._events.clear()
            self._snaps.clear()
            self._last_state = None   # 下一个 watcher step 会重新存一条初始快照
            self._exc_text = None

    # ------------------------------------------------------------------ 帧
    def on_frame(self, shot, caller=''):
        """登记一帧，返回全局 fid。数组必须拷贝（dxcam 等可能复用缓冲区）。"""
        if shot is None or shot is False:
            return self.thread_fid()

        arr = shot.copy() if self.store_frames else None

        with self._lock:
            self._seq += 1
            self._fid += 1
            fid = self._fid
            if arr is not None:
                self._frames.append({'fid': fid, 'seq': self._seq, 't': round(time.time(), 3),
                                     'thread': threading.current_thread().name,
                                     'caller': caller, 'arr': arr})
                self._prune_locked()
        self._tl.fid = fid
        return fid

    def thread_fid(self):
        """当前线程最近一次 on_frame 得到的 fid。"""
        return getattr(self._tl, 'fid', 0)

    def _prune_locked(self):
        while len(self._frames) > self.keep_frames:
            self._frames.popleft()
        oldest = self._frames[0]['fid']
        # 保留「窗口起点之前最近的一条」快照，作为重放初始状态
        while len(self._snaps) >= 2 and self._snaps[1][0] <= oldest:
            self._snaps.popleft()

    # ------------------------------------------------------------------ 事件
    def log(self, src, kind, **kw):
        with self._lock:
            self._seq += 1
            # 固定的前缀字段顺序：fid, kind, src, thread, seq, t；其后是各事件自己的字段。
            # （kw 里的 fid 会覆盖值，但不改变它排第一的位置）
            ev = {'fid': self._fid, 'kind': kind, 'src': src,
                  'thread': threading.current_thread().name,
                  'seq': self._seq, 't': round(time.time(), 3)}
            ev.update(kw)
            self._events.append((self._seq, dumps_ordered(ev)))
        return ev['seq']

    def log_exception(self, src='main', exc=None):
        """把异常（类型、信息、完整 traceback，含 raise ... from 的因果链）记成一条事件。
        在 except 块里、dump() 之前调用；exc 省略时取当前正在处理的异常。"""
        import sys
        if exc is None:
            exc = sys.exc_info()[1]
        if exc is None:
            tb = '(没有正在处理的异常)'
            typ, msg = '', ''
        else:
            tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            typ, msg = type(exc).__name__, str(exc)
        with self._lock:
            self._exc_text = tb
        return self.log(src, 'exception', type=typ, msg=msg, tb=tb)

    # ------------------------------------------------------------------ 状态快照
    def add_extra(self, name, fn):
        """注册一个返回可 JSON 化 dict 的回调（watcher 私有状态、main 私有字段等）。"""
        self._extra[name] = fn

    def freeze(self, with_extra=True):
        """取 (gamestate_json, extra_json)。gamestate 被 main 线程并发修改时可能抛
        RuntimeError，重试几次；取不到返回 (None, None)。"""
        from gamestate import get_gamestate
        for _ in range(5):
            try:
                gs = dumps(get_gamestate())
                ex = dumps({n: f() for n, f in list(self._extra.items())}) if with_extra else ''
                return gs, ex
            except Exception:
                continue
        return None, None

    def record_state(self, fid, gs_json, extra_json):
        if gs_json is None:
            return
        combined = '{"gs":%s,"extra":%s}' % (gs_json, extra_json or '{}')
        with self._lock:
            if combined != self._last_state:
                self._last_state = combined
                self._snaps.append((fid, combined))

    # ------------------------------------------------------------------ dump
    def dump(self, reason='manual', folder=None, force=False):
        """把内存里的窗口落成可重放的现场目录，返回路径。2 秒内重复调用返回上次路径。"""
        if not self.store_frames:
            return None
        with self._dump_lock:
            now = time.time()
            if not force and self._last_dump and now - self._last_dump[0] < 2.0:
                return self._last_dump[1]

            # 持锁只做「拿引用」：数组创建后从不被修改，之后在锁外慢慢编码是安全的
            with self._lock:
                entries = list(self._frames)
                snaps = list(self._snaps)
                min_seq = entries[0]['seq'] if entries else 0
                events = [ln for s, ln in self._events if s >= min_seq]

            safe = re.sub(r'\W+', '_', reason)[:40]
            folder = folder or os.path.join('./logs/dump',
                                            datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + safe)
            fdir = os.path.join(folder, 'frames')
            os.makedirs(fdir, exist_ok=True)

            jobs, rows = [], []
            for e in entries:
                name = f'{e["fid"]:07d}.png'
                jobs.append((name, e['arr']))
                row = {kk: vv for kk, vv in e.items() if kk != 'arr'}
                row['file'] = name
                rows.append(row)

            def write(job):
                name, arr = job
                return name if cv2.imwrite(os.path.join(fdir, name), arr, PNG_PARAMS) else None

            failed = []
            with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
                for job, ok in zip(jobs, ex.map(lambda j: write(j), jobs)):
                    if ok is None:
                        failed.append(job[0])

            def w(name, lines):
                with open(os.path.join(folder, name), 'w', encoding='utf-8') as fp:
                    for ln in lines:
                        fp.write(ln + '\n')

            if self._exc_text:
                with open(os.path.join(folder, 'exception.txt'), 'w', encoding='utf-8') as fp:
                    fp.write(self._exc_text)
            w('frames.jsonl', [dumps_ordered(r) for r in rows])
            w('events.jsonl', events)
            w('states.jsonl', ['{"fid":%d,"state":%s}' % (fid, st) for fid, st in snaps])
            with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fp:
                json.dump({'reason': reason, 'time': datetime.now().isoformat(),
                           'frames': len(rows), 'write_failed': failed},
                          fp, ensure_ascii=False)

            try:    # 生成可直接用浏览器打开的逐帧查看器；失败不影响 dump 本身
                try:
                    from .dump_viewer import build_viewer
                except ImportError:
                    from dump_viewer import build_viewer
                build_viewer(folder)
            except Exception as e:
                print(f'[WARN] 生成 viewer.html 失败: {e!r}')

            print(f'recorder: dump {len(rows)} 帧 / {len(events)} 事件 -> {folder}')
            if failed:
                print(f'[WARN] {len(failed)} 个帧文件写盘失败: {failed[:5]}')
            if not rows:
                print('[WARN] 这次 dump 没有任何帧：get_screenshot 没有调用 '
                      'get_recorder().on_frame(shot, caller)，请确认 screenshot.py 已按新版更新')
            self._last_dump = (time.time(), folder)
            return folder


_rec = None
_rec_lock = threading.Lock()


def get_recorder():
    global _rec
    if _rec is None:
        with _rec_lock:
            if _rec is None:
                _rec = Recorder()
    return _rec


def set_recorder(r):
    global _rec
    _rec = r
