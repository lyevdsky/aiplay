import queue
import threading
import time
import traceback

from screenshot import get_screenshot
from hand import check_tsumo
from kawa import rec_dahai
from meld import rec_new_meld, rec_kakan
from hora import is_interrupt, is_hora, is_ryukyoku
from gamestate import get_gamestate
from util import stable_func
from config import POLLING_INTERVAL, IS_DEV
from debug.recorder import get_recorder

# 打牌因为「同家副露尚未入队」被压住的最多帧数；超过就放行并记日志，
# 防止副露位被特效之类的画面误判后永久挡住这家打牌。
MELD_HOLD_MAX = 10


# ------------------------------------------------------------------ 单项观测
# 观测函数返回 (ctx, 结果) 或 None。把 ctx 一起放进被去抖的值里：
# 稳定判定要求「同一个 ctx 下连续 N 帧结果一致」，main 推进 kawa_index 后，
# 旧 ctx 的半成品计数不会和新格子的识别混在一起。

def _obs_dahai(shot, v):
    r = rec_dahai(shot, v['pos'], v['k'], v['ri'])
    return None if r is None else (v['ctx'], r)


def _obs_meld(shot, v):
    r = rec_new_meld(shot, v['pos'], v['melds'])
    return None if r is None else (v['ctx'], r)


def _obs_kakan(shot, v):
    r = rec_kakan(shot, v['pos'], v['melds'])
    return None if r is None else (v['ctx'], r)


class ChangeWatcher:
    """后台线程：与 main 并行，持续在同一帧上跑全部识别，把识别结果推入队列；
    main 在对应 phase 按需 peek / 取出。

    设计原则：
    - 单写者：gamestate 只有 main 写，watcher 只读。
    - 每家（pid 0..3）独立识别「下一个牌河格」和「下一个副露位」，
      各有自己的队列槽：dahai_q[pid] / meld_q[pid]。
    - 队列非空 = 「已识别，待 main 消费」，此时不再识别该项；被消费后才重新开始。
      因此不需要 keep_latest 覆盖（方法保留）。
    - 事件带 ctx（pid + kawa_index + 副露类型序列），ctx 取自本帧开头的一次性快照，
      与识别所用参数同源；main 侧 ctx 对不上的事件视为陈旧并丢弃（见 peek / take）。
    - 唯一的私有状态是 stable 去抖实例（按 (pid, kind) 持有），不含业务状态。

    队列：
    - tsumo_q      : 自己摸牌
    - dahai_q[pid] : 该玩家在其 kawa_index 格的打牌
    - meld_q[pid]  : 该玩家在其下一副露位的新副露（吃/碰/暗杠/大明杠/加杠）
    - end_q        : 终局中断（hora / ryukyoku）
    - player_q     : 暂不使用（active bar 已移除），仅为兼容保留

    可复现性：一轮识别 = step(shot, fid)，只依赖 (帧, gamestate, stable 实例状态,
    队列内容)，不取帧、不 sleep、不阻塞。
    """

    def __init__(self, manual=False):
        # manual=True：不起线程，由外部（回放测试的虚拟时钟）调用 manual_step() 驱动
        self.manual = manual
        self.player_q = queue.Queue()
        self.tsumo_q = queue.Queue()
        self.end_q = queue.Queue()
        self.dahai_q = [queue.Queue() for _ in range(4)]
        self.meld_q = [queue.Queue() for _ in range(4)]

        self._queues = {
            'player_q': self.player_q,
            'tsumo_q': self.tsumo_q,
            'end_q': self.end_q,
        }
        for i in range(4):
            self._queues[f'dahai_q{i}'] = self.dahai_q[i]
            self._queues[f'meld_q{i}'] = self.meld_q[i]

        self._current_player = None
        self._player_to_id = None
        # 打牌因「同家副露未入队」被推迟的次数（防误判永久挡住）
        self._meld_hold = [0] * 4
        self._stable = {}                # (pid, kind) -> stable_func 实例，纯去抖
        self._running = False
        self._thread = None
        self.error = None                # 线程异常：main 应检查并抛出，避免静默卡死

        for name, q in self._queues.items():
            self._wrap_put(q, name)

        get_recorder().add_extra('watcher', self._extra)

    # ---------------------------------------------------------------- 记录相关
    def _wrap_put(self, q, name):
        """包裹队列实例的 put：入队前把事件写进 recorder。"""
        orig_put = q.put

        def put(item, *args, **kwargs):
            rec = get_recorder()
            rec.log('watcher', 'put', q=name, fid=rec.thread_fid(), item=item)
            return orig_put(item, *args, **kwargs)

        q.put = put

    def _extra(self):
        """随 gamestate 一起快照的私有状态（队列内容会影响「是否跳过识别」）。"""
        return {'current_player': self._current_player,
                'player_to_id': self._player_to_id,
                'queues': {n: list(q.queue) for n, q in self._queues.items()}}

    # ---------------------------------------------------------------- 生命周期
    def reset(self, current_player, player_to_id):
        """新一局开始时由主流程调用。reset 始终在 start 之前调用。"""
        self._current_player = current_player
        self._player_to_id = dict(player_to_id)
        self._stable = {}
        get_recorder().log('watcher', 'reset', current_player=current_player,
                           player_to_id=self._player_to_id)

    def start(self):
        if self._running:
            return
        for q in self._queues.values():
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        self.error = None
        self._running = True
        get_recorder().log('watcher', 'start')
        if self.manual:
            return
        self._thread = threading.Thread(target=self._loop, name='watcher', daemon=True)
        self._thread.start()

    def stop(self):
        was = self._running
        self._running = False
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2)
        self._thread = None
        if was:
            get_recorder().log('watcher', 'stop')

    # ---------------------------------------------------------------- 队列工具
    @staticmethod
    def _keep_latest(q, item=None):
        """（保留，当前未使用）清掉旧值，只留最新一项。"""
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        if item is not None:
            q.put(item)

    @staticmethod
    def _ctx(pid, pi):
        """事件有效性 key：玩家 id + kawa_index + 副露类型序列。"""
        return (pid, pi['kawa_index'], tuple(m['type'] for m in pi['melds']))

    def ctx_of(self, pid):
        """main 用：该玩家当前的实时 ctx。"""
        return self._ctx(pid, get_gamestate()['player_info'][pid])

    def peek(self, q, ctx):
        """main 用：看队首但不取。ctx 对不上的陈旧事件就地丢弃
        （丢弃后队列变空，watcher 随即恢复识别该项）。"""
        while True:
            with q.mutex:
                item = q.queue[0] if q.queue else None
            if item is None or item.get('ctx') == ctx:
                return item
            try:
                dropped = q.get_nowait()
                get_recorder().log('main', 'drop_stale', item=dropped, want=ctx)
            except queue.Empty:
                return None

    def take(self, q, ctx):
        """main 用：peek 且取走。取走后 watcher 才会重新识别该项，
        所以 main 必须在取走的同一处推进 kawa_index / melds。"""
        item = self.peek(q, ctx)
        if item is None:
            return None
        try:
            return q.get_nowait()
        except queue.Empty:
            return None

    # ---------------------------------------------------------------- 一轮识别
    def _st(self, pid, kind, fn, **kw):
        key = (pid, kind)
        if key not in self._stable:
            self._stable[key] = stable_func(fn, **kw)
        return self._stable[key]

    @staticmethod
    def _view(gs):
        """本帧对 4 家的一次性快照：识别参数和 ctx 都用它，避免与 main 的写入交错。"""
        view = []
        for pid in range(4):
            pi = gs['player_info'][pid]
            melds = list(pi['melds'])
            view.append({
                'pos': gs['position'][pid],
                'k': pi['kawa_index'],
                'ri': pi['riichi_index'],
                'melds': melds,
                'ctx': (pid, pi['kawa_index'], tuple(m['type'] for m in melds)),
            })
        return view

    def step(self, shot, fid):
        """对一帧做完整一轮识别。返回 out（各 check 的输出，供日志/重放比对）。"""
        rec = get_recorder()
        gs_in, ex_in = rec.freeze()
        rec.record_state(fid, gs_in, ex_in)
        out = {}
        try:
            self._step(shot, out)
        finally:
            gs_out, _ = rec.freeze(with_extra=False)
            extra = {'gs_changed': True} if gs_out != gs_in else {}
            rec.log('watcher', 'step', fid=fid, out=out, **extra)
        return out

    def _step(self, shot, out):
        # 终局中断：整轮不识别牌；end_q 为空则尝试分辨 hora / ryukyoku（非阻塞）。
        if is_interrupt(shot):
            out['interrupt'] = True
            if self.end_q.empty():
                if is_hora(shot):
                    out['end'] = 'hora'
                    self.end_q.put({'type': 'hora'})
                elif is_ryukyoku(shot):
                    out['end'] = 'ryukyoku'
                    self.end_q.put({'type': 'ryukyoku'})
            return

        gs = get_gamestate()
        view = self._view(gs)
        cur = gs['current_player']
        my_id = self._player_to_id['self']
        out['cur'] = cur

        # 自己摸牌：自己手番，或下一手轮到自己（Claim 阶段要靠它判断）
        if (cur == my_id or (cur + 1) % 4 == my_id) and self.tsumo_q.empty():
            tile = check_tsumo(shot)
            out['tsumo'] = tile
            if tile is not None:
                self.tsumo_q.put({'type': 'tsumo', 'tile': tile, 'ctx': view[my_id]['ctx']})

        # 4 家各自扫描：打牌 + 副露
        for pid in range(4):
            v = view[pid]

            # 打牌：该玩家 kawa_index 格
            if self.dahai_q[pid].empty():
                res = self._st(pid, 'dahai', _obs_dahai, stable_count=3)(shot, v)
                if res is not None and self._hold_for_meld(pid, shot, v):
                    # 这家有一手副露已经认出来、但还没进 meld_q：
                    # 打牌动画和鸣牌动画重叠时打牌会先出来，这里先压住，
                    # 等副露入队、被 main 消费之后再放。
                    out[f'dahai{pid}_hold'] = True
                    res = None
                if res is not None:
                    ctx, (tile, tsumogiri, riichi) = res
                    out[f'dahai{pid}'] = (tile, tsumogiri, riichi)
                    self.dahai_q[pid].put({'type': 'dahai', 'tile': tile,
                                           'tsumogiri': tsumogiri, 'riichi': riichi,
                                           'ctx': ctx})

            # 副露：下一副露位的新副露；没有再看已有的碰是否被加杠
            if self.meld_q[pid].empty():
                res = self._st(pid, 'meld', _obs_meld, stable_count=3)(shot, v)
                if res is None and any(m['type'] == 'pon' for m in v['melds']):
                    res = self._st(pid, 'kakan', _obs_kakan)(shot, v)
                if res is not None:
                    ctx, meld = res
                    out[f'meld{pid}'] = meld
                    meld = dict(meld)
                    meld['ctx'] = ctx
                    self.meld_q[pid].put(meld)

    def _hold_for_meld(self, pid, shot, v):
        """该玩家有一手新副露「已认出但还没入 meld_q」时返回 True，用来压住他的打牌。

        打牌动画与鸣牌动画重叠时，打牌会先被识别出来（~1-3 帧），副露则要等动画落定
        才认得出。不压住的话 main 会先看到打牌、断定「没人鸣牌」，把「鸣牌后打牌」
        当成「摸牌后打牌」，整条手番就错了。
        """
        if not self.meld_q[pid].empty():      # 副露已入队 → 顺序已经安全
            self._meld_hold[pid] = 0
            return False
        if rec_new_meld(shot, v['pos'], v['melds']) is None:
            self._meld_hold[pid] = 0
            return False
        self._meld_hold[pid] += 1
        if self._meld_hold[pid] > MELD_HOLD_MAX:   # 兜底：误判时不至于永久压住
            get_recorder().log('watcher', 'meld_hold_timeout', pid=pid,
                               n=self._meld_hold[pid])
            self._meld_hold[pid] = 0
            return False
        return True

    def _run_once(self):
        """一次迭代：取帧 → step。返回 False 表示出现异常、线程应退出。"""
        rec = get_recorder()
        try:
            shot = get_screenshot()
            if shot is not None and shot is not False:
                self.step(shot, rec.thread_fid())
        except Exception as e:
            # 异常不能让线程静默死亡，否则 main 永远等不到信号 → 表现为「卡死」。
            self.error = e
            traceback.print_exc()
            rec.log('watcher', 'crash', err=repr(e), tb=traceback.format_exc())
            rec.dump('watcher_crash')
            self._running = False
            return False
        return True

    def manual_step(self):
        """manual 模式下由外部驱动的一次迭代，等价于 _loop 的一轮。"""
        if self._running:
            self._run_once()

    def _loop(self):
        while self._running:
            if not self._run_once():
                return
            time.sleep(POLLING_INTERVAL if not IS_DEV else 0.05)
