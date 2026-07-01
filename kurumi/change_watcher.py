from datetime import datetime
import os
import threading
import queue
import time
import cv2
from screenshot import get_screenshot
from kyoku import get_active_player
from hand import check_tsumo
from kawa import check_dahai
from meld import check_new_meld, check_kakan
from hora import is_interrupt, is_hora, is_ryukyoku
from gamestate import get_gamestate
from util import stable_func
from config import POLLING_INTERVAL, IS_DEV
from collections import deque

img_q = deque(maxlen=20)

class ChangeWatcher:
    """后台线程：与 main 并行，持续在同一帧上跑全部识别，把时序信号按类型
    推入各自的队列；main 在对应 phase 主动从它需要的队列取/等数据。

    产出 5 类信号 / 5 个队列：
    - self.q       : player_change（盯 active bar，沿用自维护 _current_player 去重）
    - self.tsumo_q : 自己摸牌
    - self.dahai_q : 当前玩家打牌
    - self.meld_q  : 副露（check_new_meld 吃/碰/暗杠/大明杠 + check_kakan 加杠）
    - self.end_q   : 终局中断（hora / ryukyoku），由 watcher 阻塞分辨后入队

    设计约束：
    - 不产 mjai 事件；终局中断由 watcher 全权识别：is_interrupt 一旦命中，
      就阻塞分辨出 hora / ryukyoku 推入 end_q；中断期间整轮不识别牌，
      避免吃碰杠/终局动画被误判成打牌。main 只按各队列更新游戏进程，不做识别。
    - 去重沿用现有退避：某队列还有未被 main 消费的事件，就不再跑对应的 check。
    - 直接复用模块级 check_tsumo/check_dahai/check_new_meld/check_kakan——这些
      check 本就只有一处调用，调用方从 main 改成 watcher，故无共享状态冲突。
    - watcher 是 dev 单游标的唯一推进者：每轮 get_screenshot 抓一帧，所有识别
      共用这一帧（避免撕裂）；main 不再为识别取帧。
    """

    def __init__(self):
        self.q = queue.Queue()           # player_change
        self.tsumo_q = queue.Queue()
        self.dahai_q = queue.Queue()
        self.meld_q = queue.Queue()
        self.end_q = queue.Queue()       # 终局中断 hora / ryukyoku
        self._current_player = None      # 线程内记录的当前手番（绝对 id），仅 player_change 用
        self._player_to_id = None        # position 名 -> id 的映射
        self._running = False
        self._thread = None

        # 线程私有的去抖实例，避免与主流程共用 stable_func 闭包状态
        self._stable_active = stable_func(get_active_player)

    def reset(self, current_player, player_to_id):
        """新一局开始时由主流程调用，设置手番基准。线程是每局一条，
        终局由主流程调用 stop() 回收，reset 后需重新 start。
        reset 始终在 start 之前调用，线程存活期间只有它自己读写这些字段，
        不存在并发，故无需加锁。"""
        self._current_player = current_player
        self._player_to_id = dict(player_to_id)
        # 复位去抖实例，丢弃上一手番残留的采样
        self._stable_active = stable_func(get_active_player)

    def start(self):
        """启动一条新监视线程。线程生命周期与一局同步：终局由主流程
        调用 stop() 回收，下一局在 reset 后再次调用本方法新建线程。"""
        if self._running:
            return
        # 清空各队列，避免之前对局异常终止，残留
        for q in (self.q, self.tsumo_q, self.dahai_q, self.meld_q, self.end_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监视线程并等待其退出。一局结束 / 异常中止时务必调用：
        daemon 线程不会随单局自动回收 """
        self._running = False
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2)
        self._thread = None

    def _loop(self):
        while self._running:
            shot = get_screenshot()
            img_q.append(shot)
            if shot is None or shot is False:
                time.sleep(POLLING_INTERVAL)
                continue

            # 终局中断：一旦进入中断动画，整轮不再识别牌（吃碰杠/终局动画极易
            # 被误判成打牌），并阻塞分辨出 hora / ryukyoku 推入 end_q（此局已
            # 结束，watcher 无需再做别的）。end_q 非空则不重复分辨。
            if is_interrupt(shot):
                if self.end_q.empty():
                    while self._running:
                        if is_hora():
                            self.end_q.put({'type': 'hora'})
                            break
                        if is_ryukyoku():
                            self.end_q.put({'type': 'ryukyoku'})
                            break
                        time.sleep(0.5)
                time.sleep(POLLING_INTERVAL)
                continue

            gs = get_gamestate()
            cur = gs['current_player']

            # player_change：盯 active bar，自维护 _current_player 去重；
            # 队列尚有未消费信号则跳过，避免重复推送。
            if self.q.empty():
                active = self._stable_active(shot)
                if active is not None:
                    pid = self._player_to_id[active]
                    if pid != self._current_player:
                        self._current_player = pid
                        self.q.put({'type': 'player_change', 'pid': pid})
                        print(f'change_watcher: player change to {pid}')

            # 摸牌：rec_tsumo 看自己手牌的摸牌位，只有自己摸牌才识别得到。
            if self.tsumo_q.empty():
                tile = check_tsumo(shot)
                if tile is not None:
                    self.tsumo_q.put({'type': 'tsumo', 'pid': cur, 'tile': tile})

            # 打牌：当前玩家牌河下一张。前置条件 current_player != last_player
            # 当前玩家一旦打牌，main 会把 last_player 置为它，于是停检，直到手番
            # 转移；天然避免重复识别同一张打牌。
            if cur != gs['last_player'] and self.dahai_q.empty():
                res = check_dahai(shot)
                if res is not None:
                    tile, tsumogiri, riichi = res
                    self.dahai_q.put({'type': 'dahai', 'pid': cur, 'tile': tile,
                                      'tsumogiri': tsumogiri, 'riichi': riichi})

            # 副露：新副露（吃/碰/暗杠/大明杠）与加杠分别识别，二者互斥。
            # meld 本身就带 type（chi/pon/ankan/daiminkan/kakan），直接入队，
            # main 按 type 分派即可。
            if self.meld_q.empty():
                meld = check_new_meld(shot) or check_kakan(shot)
                if meld is not None:
                    self.meld_q.put(meld)

            time.sleep(POLLING_INTERVAL)

    def save_img_q(self):
        folder_name = './logs/change_watcher/' + datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(folder_name, exist_ok=True)

        items = list(img_q)
        img_q.clear()
        idx = 0
        for img in items:
            filename = os.path.join(folder_name, f"{idx:04d}.jpg")
            ok, buf = cv2.imencode('.jpg', img)
            if not ok:
                print(f"change_watcher: 第 {idx} 帧编码失败，跳过")
                continue
            buf.tofile(filename)
            idx += 1

        print(f"共保存 {idx} 张图片到文件夹 {folder_name}")
