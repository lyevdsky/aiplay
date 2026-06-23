"""跑完测试数据（dev 下即 ./video/kyo.mp4），打印 ChangeWatcher 生成的 q 队列。

直接复用 ChangeWatcher 的逐帧判定逻辑，但同步驱动：
- 不起后台线程、不 sleep、不做「队列非空就暂停取帧」的 dev 同步暂停
  （那只是回放时与 main 对齐节奏用的，与产出的时序信号无关）；
- 用 watcher 自己的取帧入口 get_raw_frame()，读到 False/None 即视为数据跑完。

用法：cd kurumi && python test_change_watcher.py
"""
import cv2
from screenshot import get_raw_frame
from hora import is_interrupt, is_hora, is_ryukyoku
from change_watcher import ChangeWatcher


def run_over_test_data(current_player=0,
                       player_to_id=None,
                       max_frames=100000):
    if player_to_id is None:
        # 仅为演示队列产出，用恒等映射；真实运行时由 rec_kyoku_info 推出
        player_to_id = {'self': 0, 'next': 1, 'across': 2, 'prev': 3}

    w = ChangeWatcher()
    w.reset(current_player, player_to_id)
    w._running = True  # _resolve_interrupt 的循环条件需要它

    events = []          # 与 w.q 同步留存，便于最后统一打印
    frames = 0

    for frames in range(1, max_frames + 1):
        shot = get_raw_frame()
        print(f'\r已取帧 {frames}', end='', flush=True)
        if shot is None or shot is False:
            print(f'\n帧源耗尽，于第 {frames} 帧停止')
            break

        # 中断即一局终点：解析出 hora/ryukyoku 后推送并结束
        if is_interrupt(shot):
            cv2.imwrite('interrupt.png', shot)
            interrupt = _resolve_interrupt(w)
            if interrupt is not None:
                ev = {'type': interrupt}
                w.q.put(ev)
                events.append((frames, ev))
                print(f'[帧 {frames}] 中断 -> {interrupt}，结束')
                break
            else:
                print(f'[帧 {frames}] 检测到中断但数据已耗尽，无法定型')
                break

        active = w._stable_active(shot)
        if active is not None:
            pid = player_to_id[active]
            if pid != w._current_player:
                # 正常手番是传给下家（pid+1）。亮起的不是顺序下家时，
                # 多半是吃/碰/杠跳了手番，给出提示信号。
                expected = (w._current_player + 1) % 4
                ev = {'type': 'player_change', 'pid': pid, 'active': active}
                if pid != expected:
                    ev['out_of_order'] = True
                    ev['expected'] = expected
                    ev['from'] = w._current_player
                w._current_player = pid
                w.q.put(ev)
                events.append((frames, ev))
                if ev.get('out_of_order'):
                    print(f'[帧 {frames}] !! 非顺序手番 player_change -> pid={pid} '
                          f'({active})，期望下家 pid={expected}')
                else:
                    print(f'[帧 {frames}] player_change -> pid={pid} ({active})')

    print('\n========== q 队列最终内容 ==========')
    print(f'共处理 {frames} 帧，产出 {len(events)} 个信号\n')
    for i, (fno, ev) in enumerate(events):
        print(f'{i:02d}  @帧{fno:<6} {ev}')
    return events


def _resolve_interrupt(w):
    """复刻 ChangeWatcher._resolve_interrupt，但数据耗尽即返回 None，避免死循环。"""
    while w._running:
        shot = get_raw_frame()
        if shot is None or shot is False:
            return None
        if is_hora(shot):
            return 'hora'
        if is_ryukyoku(shot):
            return 'ryukyoku'
    return None


if __name__ == '__main__':
    run_over_test_data()
