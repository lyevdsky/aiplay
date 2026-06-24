"""跑完测试数据（dev 下即 ./video/kyo.mp4），打印 ChangeWatcher 生成的 q 队列。

直接复用 ChangeWatcher 的逐帧判定逻辑，但同步驱动：
- 不起后台线程、不 sleep、不做「队列非空就暂停取帧」的 dev 同步暂停
  （那只是回放时与 main 对齐节奏用的，与产出的时序信号无关）；
- 用 watcher 自己的取帧入口 get_raw_frame()，读到 False/None 即视为数据跑完。

用法：cd kurumi && python test_change_watcher.py
"""
import queue

import cv2
from screenshot import get_raw_frame
from change_watcher import ChangeWatcher


def run_over_test_data(current_player=0,
                       player_to_id=None,
                       max_frames=100000):
    if player_to_id is None:
        # 仅为演示队列产出，用恒等映射；真实运行时由 rec_kyoku_info 推出
        player_to_id = {'self': 0, 'next': 1, 'across': 2, 'prev': 3}

    w = ChangeWatcher()
    w.q.put({'type': 'player_change', 'pid': 1 })
    w.reset(current_player, player_to_id)
    w.start()
    events = []          # 与 w.q 同步留存，便于最后统一打印
    frames = 0
    while frames < max_frames:
        frames += 1
        print(f'\r已取帧 {frames}', end='', flush=True)
        while True:
            try:
                res = w.q.get(timeout=0.5)
                break
            except queue.Empty:
                pass
        events.append((frames, res))
    
    print('\n========== q 队列最终内容 ==========')
    print(f'共处理 {frames} 帧，产出 {len(events)} 个信号\n')
    for i, (fno, ev) in enumerate(events):
        print(f'{i:02d}  @帧{fno:<6} {ev}')
    # expected = (w._current_player + 1) % 4
                # if pid != expected:
    return events

if __name__ == '__main__':
    run_over_test_data(1, {'self': 3, 'next': 0, 'across': 1, 'prev': 2}, max_frames = 204)
