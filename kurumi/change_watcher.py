from datetime import datetime
import os
import threading
import queue
import time
import cv2
from screenshot import get_raw_frame, align_reader_cursor
from kyoku import get_active_player
from util import stable_func
from config import POLLING_INTERVAL, IS_DEV
from collections import deque

img_q = deque(maxlen=20)

class ChangeWatcher:
    """后台线程：持续盯 active bar，把 player_change 时序信号按序推入队列。

    设计约束：
    - 只产 player_change 信号，不产 mjai 事件，也不再判定终局中断
      （hora/ryukyoku 已移回主流程 game.main 自行识别）。
    - 自维护 current_player（绝对值，0~3）。只有亮起的玩家 != 自己记录的
      current_player 时才推 player_change，避免重复推送。
    - 用自己独立的 stable_func 实例，不与主流程共用闭包计数器。
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
        # dev/replay：start_kyoku 已用 main 游标读过开局信息，watcher 游标
        # 须对齐到 main 当前位置，否则会从头读到开局前的过期帧。
        align_reader_cursor('watcher', 'main')
        # 清空q队列，避免之前对局异常终止，残留
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监视线程并等待其退出。一局结束 / 异常中止时务必调用：
        daemon 线程不会随单局自动回收，残留线程会和下一局的新线程
        并行抢同一帧源游标。join 有超时，避免极端情况下卡住调用方。"""
        self._running = False
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2)
        self._thread = None

    def _loop(self):
        while self._running:
            # 队列尚有未消费信号时暂停取帧（不动游标），等 main 消费完再继续，
            # 使两个读取者的取帧进度大致同步。
            # TODO 问题是重启时 在watcher追main的那个过程里，main也在loop check_interrupt. 导致main跳过了可以识别摸牌牌的那几帧
            # 所以还是要唯一游标，完全同步。
            if not self.q.empty():
                time.sleep(POLLING_INTERVAL)
                continue

            shot = get_raw_frame()
            img_q.append(shot)
            if shot is None or shot is False:
                time.sleep(POLLING_INTERVAL)
                continue

            active = self._stable_active(shot)
            if active is not None:
                pid = self._player_to_id[active]
                if pid != self._current_player:
                    # 队列尚有未消费信号时就不put，等main追上帧进度
                    # 在取帧前暂缓的话会虽然同步了但也导致了停下了，测试环境还得追上main。 而卡在put之前，而不是put完stop，可让watcher始终走在main前面
                    # 不对不对，只要watcher是按帧顺序取的话，是不会产生错误的！顺序没有问题，
                    # 问题是，在watcher追main的那个过程里，main也在loop check_interrupt. 导致main跳过了可以识别摸牌牌的那几帧
                    # 所以解决方式是一、让main停下来等watcher追上，这是不行的，正式环境没有这么傻逼的操作，不知道是interrupt还是change player
                    # 二、还是之前的想法，让watcher解耦main的逻辑，不等main或至少在main前面，那么就是sleep在获取了active后put前。而不是check active 前sleep。
                    # TODO问题是卡在这里，新一局时会仍然put上一局生成的事件！不管卡哪都一样
                    # while not self.q.empty():
                    #     if not self._running:
                    #         return
                    #     time.sleep(POLLING_INTERVAL)
                    self._current_player = pid
                    self.q.put({'type': 'player_change', 'pid': pid})
                    text = f'change_watcher: player change to {pid}'
                    print(text)

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
