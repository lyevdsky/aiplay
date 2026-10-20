import queue
import threading
import time
import traceback

from screenshot import get_screenshot
from kyoku import get_active_player
from hand import check_tsumo
from kawa import check_dahai
from meld import check_new_meld, check_kakan
from hora import is_interrupt, is_hora, is_ryukyoku
from gamestate import get_gamestate
from util import stable_func
from config import POLLING_INTERVAL, IS_DEV
from debug.recorder import get_recorder

QUEUE_NAMES = ('player_q', 'tsumo_q', 'dahai_q', 'meld_q', 'end_q')


class ChangeWatcher:
    """后台线程：与 main 并行，持续在同一帧上跑全部识别，把时序信号按类型
    推入各自的队列；main 在对应 phase 主动从它需要的队列取/等数据。

    产出 5 类信号 / 5 个队列：
    - player_q : player_change（盯 active bar，沿用自维护 _current_player 去重）
    - tsumo_q  : 自己摸牌
    - dahai_q  : 当前玩家打牌
    - meld_q   : 副露（check_new_meld 吃/碰/暗杠/大明杠 + check_kakan 加杠）
    - end_q    : 终局中断（hora / ryukyoku）

    可复现性设计：
    - 一轮识别 = step(shot, fid)：只依赖 (帧, gamestate, 自身私有状态, 队列内容)，
      不取帧、不 sleep、不阻塞。_loop 只是「取帧 → step → sleep」。
      终局中断不再阻塞等待，而是每个 step 尝试分辨一次，语义等价。
    - 每个 step 开头把 gamestate + 私有状态快照写入 recorder，结尾写 step 事件
      （含各 check 的输出，None 也记）。replay.py 用同一个 step 重放并逐帧比对。
    """

    def __init__(self):
        self.player_q = queue.Queue()
        self.tsumo_q = queue.Queue()
        self.dahai_q = queue.Queue()
        self.meld_q = queue.Queue()
        self.end_q = queue.Queue()
        self._current_player = None
        self._player_to_id = None
        self._running = False
        self._thread = None
        self.error = None                # 线程异常：main 应检查并抛出，避免静默卡死

        for name in QUEUE_NAMES:
            self._wrap_put(getattr(self, name), name)

        self._stable_active = stable_func(get_active_player)
        get_recorder().add_extra('watcher', self._extra)

    # ---------------------------------------------------------------- 记录相关
    def _wrap_put(self, q, name):
        """包裹队列实例的 put：入队前把事件写进 recorder（含 _keep_latest 的覆盖写）。"""
        orig_put = q.put

        def put(item, *args, **kwargs):
            rec = get_recorder()
            rec.log('watcher', 'put', q=name, fid=rec.thread_fid(), item=item)
            return orig_put(item, *args, **kwargs)

        q.put = put

    def _extra(self):
        """随 gamestate 一起快照的私有状态（队列内容会影响「是否跳过 check」）。"""
        return {'current_player': self._current_player,
                'player_to_id': self._player_to_id,
                'queues': {n: list(getattr(self, n).queue) for n in QUEUE_NAMES}}

    # ---------------------------------------------------------------- 生命周期
    def reset(self, current_player, player_to_id):
        """新一局开始时由主流程调用，设置手番基准。reset 始终在 start 之前调用。"""
        self._current_player = current_player
        self._player_to_id = dict(player_to_id)
        self._stable_active = stable_func(get_active_player)
        get_recorder().log('watcher', 'reset', current_player=current_player,
                           player_to_id=self._player_to_id)

    def start(self):
        if self._running:
            return
        for name in QUEUE_NAMES:
            q = getattr(self, name)
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        self.error = None
        self._running = True
        get_recorder().log('watcher', 'start')
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

    @staticmethod
    def _keep_latest(q, item=None):
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

    # ---------------------------------------------------------------- 一轮识别
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
        # 终局中断：整轮不识别牌；end_q 为空则尝试分辨 hora / ryukyoku（非阻塞，
        # 分辨不出就下一帧再试）。
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
        cur = gs['current_player']
        out['cur'], out['last'] = cur, gs['last_player']

        # player_change
        if self.player_q.empty():
            active = self._stable_active(shot)
            out['active'] = active
            if active is not None:
                pid = self._player_to_id[active]
                if pid != self._current_player:
                    self._current_player = pid
                    self.player_q.put({'type': 'player_change', 'pid': pid})

        # 摸牌：只在自己手番识别；tsumo_q 只保留最新一次
        my_id = self._player_to_id['self']
        if self._current_player == my_id:
            tile = check_tsumo(shot)
            out['tsumo'] = tile
            if tile is not None:
                self._keep_latest(self.tsumo_q, {'type': 'tsumo', 'tile': tile,
                                                 'ctx': self._ctx(my_id, gs['player_info'][my_id])})
        else:
            self._keep_latest(self.tsumo_q)

        # 打牌
        if cur != gs['last_player']:
            res = check_dahai(shot)
            out['dahai'] = res
            if res is not None:
                tile, tsumogiri, riichi = res
                self._keep_latest(self.dahai_q, {'type': 'dahai', 'tile': tile,
                                                 'tsumogiri': tsumogiri, 'riichi': riichi,
                                                 'ctx': self._ctx(cur, gs['player_info'][cur])})

        # 副露
        if cur != gs['last_player']:
            meld = check_new_meld(shot) or check_kakan(shot)
            out['meld'] = meld
            if meld is not None:
                meld['ctx'] = self._ctx(cur, gs['player_info'][cur])
                self._keep_latest(self.meld_q, meld)

    def _loop(self):
        def sleep():
            time.sleep(POLLING_INTERVAL if not IS_DEV else 0.05)

        rec = get_recorder()
        while self._running:
            try:
                shot = get_screenshot()
                if shot is None or shot is False:
                    sleep()
                    continue
                self.step(shot, rec.thread_fid())
            except Exception as e:
                # 以前这里一旦抛异常线程静默死亡，main 永远等不到信号 → 表现为「卡死」。
                self.error = e
                traceback.print_exc()
                rec.log('watcher', 'crash', err=repr(e), tb=traceback.format_exc())
                rec.dump('watcher_crash')
                self._running = False
                return
            sleep()
