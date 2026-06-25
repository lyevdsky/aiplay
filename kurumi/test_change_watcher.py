"""跑完测试数据（dev 下即 ./video/kyo.mp4），打印 ChangeWatcher 生成的 q 队列。

起真实的 ChangeWatcher 后台线程，按生产方式从 q 消费时序信号。
新的单游标模型下，游标只由 main 侧的 advance_cursor 推动；本测试没有 main，
故用一个「驱动线程」按 POLLING_INTERVAL 节奏推进游标、模拟 main 逐帧消费视频
（与 watcher 取帧 ~1:1）。驱动线程读到 False/None 即视为测试数据跑完，停掉
自身与 watcher；watcher 若先因终局中断自退，消费循环也会收工。

用法：cd kurumi && python test_change_watcher.py
"""
import queue
import threading
import time

from screenshot import get_raw_frame, advance_cursor
from change_watcher import ChangeWatcher
from config import POLLING_INTERVAL


def run_over_test_data(current_player=0,
                       player_to_id=None,
                       max_signals=100000):
    if player_to_id is None:
        # 仅为演示队列产出，用恒等映射；真实运行时由 rec_kyoku_info 推出
        player_to_id = {'self': 0, 'next': 1, 'across': 2, 'prev': 3}

    w = ChangeWatcher()
    w.reset(current_player, player_to_id)
    w.start()        # 内部会先清空 q，故无需手动预置信号

    # 游标驱动：模拟 main 每 POLLING_INTERVAL 取一帧推进一次游标，
    # 读到 False/None 即数据耗尽，顺手停掉 watcher。
    done = threading.Event()

    def drive():
        while not done.is_set():
            advance_cursor()
            shot = get_raw_frame()
            if shot is None or shot is False:
                break
            time.sleep(POLLING_INTERVAL)
        done.set()
        w.stop()

    threading.Thread(target=drive, daemon=True).start()

    events = []
    while len(events) < max_signals:
        try:
            ev = w.q.get(timeout=0.2)
        except queue.Empty:
            # 数据耗尽，或 watcher 终局自退且队列已空 -> 收工
            if done.is_set() or not w._running:
                break
            continue
        events.append(ev)
        print(f'\r已收信号 {len(events)}', end='', flush=True)

    done.set()
    w.stop()
    # 收尾：取走队列里可能残留的信号
    while True:
        try:
            events.append(w.q.get_nowait())
        except queue.Empty:
            break

    print('\n========== q 队列最终内容 ==========')
    print(f'产出 {len(events)} 个信号\n')
    for i, ev in enumerate(events):
        print(f'{i:02d}  {ev}')
    return events


if __name__ == '__main__':
    run_over_test_data(1, {'self': 3, 'next': 0, 'across': 1, 'prev': 2})
