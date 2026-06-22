import threading
import queue
import time

from screenshot import get_raw_frame
from kyoku import get_active_player
from hora import is_interrupt, is_hora, is_ryukyoku
from util import stable_func
from config import POLLING_INTERVAL


class ChangeWatcher:
    """后台线程：持续盯 active bar 和中断动画，把时序信号按序推入队列。

    设计约束：
    - 只产时序信号（player_change / hora / ryukyoku），不产 mjai 事件。
      具体打了什么牌、什么副露，仍由主流程识别并按序 emit。
    - 自维护 current_player（绝对值，0~3）。只有亮起的玩家 != 自己记录的
      current_player 时才推 player_change，避免重复推送。
    - 用自己独立的 stable_func 实例，不与主流程共用闭包计数器。
    - 中断（hora/ryukyoku）与 player_change 共用同一队列，主流程按序消费。
    """

    def __init__(self):
        self.q = queue.Queue()
        self._current_player = None      # 线程内记录的当前手番（绝对 id）
        self._player_to_id = None        # position 名 -> id 的映射
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._interrupt_sent = False     # 一次中断只推一次，等 reset 清除

        # 线程私有的去抖实例，避免与主流程共用 stable_func 闭包状态
        self._stable_active = stable_func(get_active_player)

    def reset(self, current_player, player_to_id):
        """新一局/手番变更时由主流程调用，复位线程记录的手番基准。"""
        with self._lock:
            self._current_player = current_player
            self._player_to_id = dict(player_to_id)
            self._interrupt_sent = False
        # 复位去抖实例，丢弃上一手番残留的采样
        self._stable_active = stable_func(get_active_player)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            shot = get_raw_frame()
            if shot is None or shot is False:
                time.sleep(POLLING_INTERVAL)
                continue

            # 1. 中断优先：荣和/自摸/流局时 bar 不会正常轮转
            if not self._interrupt_sent and is_interrupt(shot):
                interrupt = self._resolve_interrupt()
                if interrupt is not None:
                    with self._lock:
                        self._interrupt_sent = True
                    self.q.put({'type': interrupt})
                    time.sleep(POLLING_INTERVAL)
                    continue

            # 2. active bar：从亮的状态就连续盯着，转换一完成立刻入队
            active = self._stable_active(shot)
            if active is not None:
                with self._lock:
                    player_to_id = self._player_to_id
                    current = self._current_player
                if player_to_id is not None and active in player_to_id:
                    pid = player_to_id[active]
                    if pid != current:
                        # 抢先把记录改掉，避免同一次切换连推多条
                        with self._lock:
                            self._current_player = pid
                        self.q.put({'type': 'player_change', 'pid': pid})

            time.sleep(POLLING_INTERVAL)

    def _resolve_interrupt(self):
        """区分 hora / ryukyoku。这里允许短暂等待动画定型，
        但不阻塞主流程（主流程消费的是队列）。"""
        deadline = 5.0
        elapsed = 0.0
        while elapsed < deadline and self._running:
            if is_hora():
                return 'hora'
            if is_ryukyoku():
                return 'ryukyoku'
            time.sleep(POLLING_INTERVAL)
            elapsed += POLLING_INTERVAL
        return None
