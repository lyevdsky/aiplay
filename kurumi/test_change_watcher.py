"""跑完测试数据（dev 下即 ./video/kyo.mp4），打印 ChangeWatcher 产出的各队列信号。

新模型下 watcher 自己用 get_screenshot 推进 dev 单游标、并行识别全部信号
（player_change / tsumo / dahai / meld / 终局中断 end），main 不再参与取帧或识别。
本测试没有 main，仅起真实 watcher 后台线程，按生产方式从各队列消费并打印；
end_q 拿到 hora/ryukyoku 或长时间无新信号即收工。

注意：没有 main 推进 gamestate（current_player / kawa_index 等始终是初值），
故 dahai/meld 检测只能反映「当前这一手番」的静态画面，无法跟随牌局推进——
本测试只验证 watcher 能并行产出各类信号、不崩溃。需 IS_DEV=True（或先
set_replay_folder）才会读视频而非摄像头。

用法：cd kurumi && python test_change_watcher.py
"""
import queue
import time

from change_watcher import ChangeWatcher
from gamestate import set_gamestate, init_gamestate


def run_over_test_data(current_player=0, player_to_id=None, max_signals=100000):
    if player_to_id is None:
        # 仅为演示队列产出，用恒等映射；真实运行时由 rec_kyoku_info 推出
        player_to_id = {'self': 0, 'next': 1, 'across': 2, 'prev': 3}

    # 建立 gamestate：watcher 的 tsumo/dahai/meld 检测都读它。
    init_gamestate()
    position = [''] * 4
    for name, pid in player_to_id.items():
        position[pid] = name
    set_gamestate({
        'current_player': current_player,
        'player_to_id': player_to_id,
        'position': position,
        'my_id': player_to_id['self'],
    })

    w = ChangeWatcher()
    w.reset(current_player, player_to_id)
    w.start()        # watcher 自驱：每轮 get_screenshot 推进游标、并行识别

    queues = {'player_change': w.q, 'tsumo': w.tsumo_q,
              'dahai': w.dahai_q, 'meld': w.meld_q, 'end': w.end_q}

    events = []
    idle = 0.0
    ended = False
    while len(events) < max_signals and not ended:
        got = False
        for name, q in queues.items():
            try:
                ev = q.get_nowait()
            except queue.Empty:
                continue
            got = True
            events.append((name, ev))
            print(f'已收信号 {len(events)}: [{name}] {ev}')
            if name == 'end':
                ended = True   # 终局，收工
        if got:
            idle = 0.0
        else:
            time.sleep(0.05)
            idle += 0.05
            if idle >= 5:      # 5s 无新信号（数据耗尽或卡住），收工
                break

    w.stop()
    print('\n========== 各队列最终内容 ==========')
    print(f'产出 {len(events)} 个信号\n')
    for i, (name, ev) in enumerate(events):
        print(f'{i:02d}  [{name}] {ev}')
    return events


if __name__ == '__main__':
    run_over_test_data(1, {'self': 3, 'next': 0, 'across': 1, 'prev': 2})
