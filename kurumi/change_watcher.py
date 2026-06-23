from datetime import datetime
import os
import threading
import queue
import time
import cv2
from screenshot import get_raw_frame, align_reader_cursor
from kyoku import get_active_player
from hora import is_interrupt, is_hora, is_ryukyoku
from util import stable_func
from config import POLLING_INTERVAL, IS_DEV
from collections import deque

img_q = deque(maxlen=20)

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
        self._running = False
        self._thread = None

        # 线程私有的去抖实例，避免与主流程共用 stable_func 闭包状态
        self._stable_active = stable_func(get_active_player)

    def reset(self, current_player, player_to_id):
        """新一局开始时由主流程调用，设置手番基准。线程是每局一条，
        中断（终局）后自行退出，reset 后需重新 start。
        reset 始终在 start 之前调用，线程存活期间只有它自己读写这些字段，
        不存在并发，故无需加锁。"""
        self._current_player = current_player
        self._player_to_id = dict(player_to_id)
        # 复位去抖实例，丢弃上一手番残留的采样
        self._stable_active = stable_func(get_active_player)

    def start(self):
        """启动一条新监视线程。线程生命周期与一局同步：终局中断后自退，
        下一局由主流程在 reset 后再次调用本方法新建线程。"""
        if self._running:
            return
        # dev/replay：start_kyoku 已用 main 游标读过开局信息，watcher 游标
        # 须对齐到 main 当前位置，否则会从头读到开局前的过期帧。
        align_reader_cursor('watcher', 'main')
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            # 队列尚有未消费信号时暂停取帧（不动游标），等 main 消费完再继续，
            # 使两个读取者的取帧进度大致同步。
            if not self.q.empty():
                time.sleep(POLLING_INTERVAL)
                continue

            shot = get_raw_frame()
            img_q.append(shot)
            if shot is None or shot is False:
                time.sleep(POLLING_INTERVAL)
                continue
            # TODO 流局九种九牌等，根据左上宝牌来判断对吗？
            #  中断即一局终点，推送后线程直接退出，无需等待下次 reset。
            if is_interrupt(shot): 
                print('change_watcher: interrupt')
                interrupt = self._resolve_interrupt()
                print('change_watcher: ', interrupt)
                if interrupt is not None:
                    self.q.put({'type': interrupt})
                    self._running = False
                    return

            active = self._stable_active(shot)
            if active is not None:
                pid = self._player_to_id[active]
                if pid != self._current_player:
                    self._current_player = pid
                    self.q.put({'type': 'player_change', 'pid': pid})
                    print('change_watcher: player change to ', pid)

            time.sleep(POLLING_INTERVAL)

    def _resolve_interrupt(self):
        """区分 hora / ryukyoku。这里允许短暂等待动画定型，
        但不阻塞主流程（主流程消费的是队列）。"""
        while self._running:
            # TODO 卡在这里ctrl+c 退不出来
            shot = get_raw_frame()
            img_q.append(shot)
            if is_hora(shot):
                return 'hora'
            if is_ryukyoku(shot):
                return 'ryukyoku'
            time.sleep(POLLING_INTERVAL)
        return None
    # TODO save的图片读不了
    def save_img_q(self):
        folder_name = './logs/change_watcher/' + datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(folder_name, exist_ok=True)

        items = list(img_q)
        img_q.clear()
        idx = 0
        for img in items:
            # 生成文件名，例如 0001_funcname_L42.jpg
            filename = os.path.join(folder_name, f"{idx:04d}.jpg")
            img.tofile(filename)
            idx += 1

        print(f"共保存 {idx} 张图片到文件夹 {folder_name}")
