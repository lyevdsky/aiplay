"""飞行记录仪：让 bug 现场可以被完整、无损地复现。

记录三类东西，共用一个全局单调递增的 seq（线程间的全序）：
  1. 帧   ：每次 get_screenshot 返回的帧都拿到全局 fid，后台线程以【无损 PNG】写盘，
            整帧逐像素完全相同才去重（np.array_equal，不缩放、不转 JPEG）。
            磁盘只滚动保留最近 keep_frames 帧。
  2. 事件 ：watcher 每帧的识别结果(step)、队列 put、main 的 consume/phase/mjai 等。
  3. 状态 ：每个 watcher step 开头的 gamestate + 各模块私有状态（仅变化时存）。

只在异常 / F1 / POST /game/save 时 dump()：把滚动窗口硬链接到 logs/dump/<时间>_<原因>/，
replay.py 读它做确定性重放。
"""
import json
import os
import queue
import re
import shutil
import threading
import time
from collections import deque
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
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=_jsonable)


class Recorder:
    def __init__(self, root='./logs/rolling', keep_frames=2000, queue_size=48,
                 event_maxlen=300_000, persist=True, store_frames=True):
        self.keep_frames = keep_frames
        self.persist = persist
        self.store_frames = store_frames

        self._lock = threading.RLock()
        self._dump_lock = threading.Lock()
        self._tl = threading.local()
        self._seq = 0
        self._fid = 0

        self._frames = deque()               # 帧索引条目(dict)，按到达顺序
        self._events = deque(maxlen=event_maxlen)   # (seq, json_line)
        self._snaps = deque()                # (fid, combined_state_json)
        self._last_state = None
        self._extra = {}                     # name -> callable，返回需随快照保存的私有状态
        self._last_dump = None               # (t, path)
        self.dropped = 0

        self._refs = {}                      # file -> 被窗口内多少条目引用
        self._last_arr = None                # 编码线程独占：上一张已处理帧，做整帧去重
        self._last_file = None

        self.session = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._ev_fp = None
        if persist:
            self.session_dir = os.path.join(root, self.session)
            self.frame_dir = os.path.join(self.session_dir, 'frames')
            os.makedirs(self.frame_dir, exist_ok=True)
            self._ev_fp = open(os.path.join(self.session_dir, 'events.jsonl'), 'a',
                               encoding='utf-8', buffering=1)
        self._q = queue.Queue(maxsize=queue_size)
        if persist and store_frames:
            threading.Thread(target=self._encoder_loop, name='rec-encoder', daemon=True).start()

    # ------------------------------------------------------------------ 帧
    def on_frame(self, shot, caller=''):
        """登记一帧，返回全局 fid。必须拷贝：dxcam 等可能复用缓冲区。"""
        if shot is None or shot is False:
            return self.thread_fid()
        arr = shot.copy() if (self.persist and self.store_frames) else None
        with self._lock:
            self._seq += 1
            self._fid += 1
            fid = self._fid
            if arr is not None:
                entry = {'fid': fid, 'seq': self._seq, 't': round(time.time(), 3),
                         'thread': threading.current_thread().name, 'caller': caller,
                         'file': None, 'dropped': False}
                self._frames.append(entry)
                try:
                    # 与 append 在同一把锁内入队 → 编码线程处理顺序 == 索引顺序
                    self._q.put_nowait((entry, arr))
                except queue.Full:
                    entry['dropped'] = True
                    self.dropped += 1
                    self.log('rec', 'frame_dropped', fid=fid)
        self._tl.fid = fid
        return fid

    def thread_fid(self):
        """当前线程最近一次 on_frame 得到的 fid。"""
        return getattr(self._tl, 'fid', 0)

    def _encoder_loop(self):
        while True:
            entry, arr = self._q.get()
            try:
                if (self._last_arr is not None and arr.shape == self._last_arr.shape
                        and np.array_equal(arr, self._last_arr)):
                    fname = self._last_file          # 整帧逐像素相同，复用文件
                else:
                    fname = f'{entry["fid"]:07d}.png'
                    if not cv2.imwrite(os.path.join(self.frame_dir, fname), arr, PNG_PARAMS):
                        raise IOError(f'imwrite failed: {fname}')
                    old = self._last_file
                    self._last_arr, self._last_file = arr, fname
                    with self._lock:
                        self._maybe_delete(old)
                with self._lock:
                    entry['file'] = fname
                    self._refs[fname] = self._refs.get(fname, 0) + 1
                    self._prune_locked()
            except Exception as e:
                entry['error'] = repr(e)
                self.log('rec', 'encode_error', fid=entry['fid'], err=repr(e))
            finally:
                self._q.task_done()

    def _maybe_delete(self, fname):
        if fname and self._refs.get(fname, 0) <= 0 and fname != self._last_file:
            try:
                os.remove(os.path.join(self.frame_dir, fname))
            except OSError:
                pass
            self._refs.pop(fname, None)

    def _prune_locked(self):
        while len(self._frames) > self.keep_frames:
            e = self._frames[0]
            if e['file'] is None and not e['dropped'] and 'error' not in e:
                break                                   # 还没编码完，不动
            self._frames.popleft()
            f = e['file']
            if f:
                self._refs[f] -= 1
                self._maybe_delete(f)
        if self._frames:
            oldest = self._frames[0]['fid']
            # 保留「窗口起点之前最近的一条」快照，作为重放初始状态
            while len(self._snaps) >= 2 and self._snaps[1][0] <= oldest:
                self._snaps.popleft()

    def _drain(self, timeout):
        end = time.time() + timeout
        while self._q.unfinished_tasks and time.time() < end:
            time.sleep(0.02)

    # ------------------------------------------------------------------ 事件
    def log(self, src, kind, **kw):
        with self._lock:
            self._seq += 1
            ev = {'seq': self._seq, 't': round(time.time(), 3), 'src': src, 'kind': kind,
                  'thread': threading.current_thread().name, 'fid': self._fid}
            ev.update(kw)
            line = dumps(ev)
            self._events.append((self._seq, line))
            if self._ev_fp:
                try:
                    self._ev_fp.write(line + '\n')
                except Exception:
                    pass
        return ev['seq']

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
    @staticmethod
    def _link(src, dst):
        try:
            os.link(src, dst)            # 硬链接：瞬间完成，且滚动删除不影响 dump
        except OSError:
            shutil.copy2(src, dst)

    def dump(self, reason='manual', folder=None, force=False):
        """把当前滚动窗口落成可重放的现场目录，返回路径。2 秒内重复调用返回上次路径。"""
        if not (self.persist and self.store_frames):
            return None
        with self._dump_lock:
            now = time.time()
            if not force and self._last_dump and now - self._last_dump[0] < 2.0:
                return self._last_dump[1]
            self._drain(5.0)
            safe = re.sub(r'\W+', '_', reason)[:40]
            folder = folder or os.path.join('./logs/dump',
                                            datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + safe)
            fdir = os.path.join(folder, 'frames')
            os.makedirs(fdir, exist_ok=True)
            with self._lock:     # 持锁期间滚动删除不会发生
                frames = [dict(e) for e in self._frames]
                snaps = list(self._snaps)
                min_seq = frames[0]['seq'] if frames else 0
                events = [ln for s, ln in self._events if s >= min_seq]
                for f in {e['file'] for e in frames if e.get('file')}:
                    self._link(os.path.join(self.frame_dir, f), os.path.join(fdir, f))
                dropped = self.dropped

            def w(name, lines):
                with open(os.path.join(folder, name), 'w', encoding='utf-8') as fp:
                    for ln in lines:
                        fp.write(ln + '\n')

            w('frames.jsonl', [dumps(e) for e in frames])
            w('events.jsonl', events)
            w('states.jsonl', ['{"fid":%d,"state":%s}' % (fid, st) for fid, st in snaps])
            with open(os.path.join(folder, 'meta.json'), 'w', encoding='utf-8') as fp:
                json.dump({'reason': reason, 'time': datetime.now().isoformat(),
                           'frames': len(frames), 'dropped_frames': dropped}, fp, ensure_ascii=False)
            print(f'recorder: dump {len(frames)} 帧 / {len(events)} 事件 -> {folder}')
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
