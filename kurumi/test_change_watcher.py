"""跑完测试数据（dev 下即 screenshot.py 里配置的视频），把 ChangeWatcher
每个队列的「每一次 put」都打印出来，并给每条打印带上帧号；结束后用
save_img_q 把 watcher 走过的每一帧存盘。帧号 = 该帧在 screenshot.img_q 里
的下标，而 save_img_q 正是按这个下标命名文件（{idx:04d}_..._loop_L117.png），
所以打印里的 [frame N] 直接对应存盘目录里的 000N_*.png，方便回查对应的图。

原理：watcher 是本测试里唯一的取帧者，每轮 _loop 调 get_screenshot 抓一帧
追加进 screenshot.img_q（终局分辨里的 is_hora/is_ryukyoku 也走同一个 img_q）。
我们把 watcher 五个队列实例的 put 方法包一层，put 触发时读 len(img_q)-1 当帧号
先打印再入队；帧号与存盘下标天然对齐。

注意：没有 main 推进 gamestate（current_player / kawa_index 等始终是初值），
故 dahai/meld 检测只能反映「当前这一手番」的静态画面，无法跟随牌局推进——
本测试只验证 watcher 能并行产出各类信号、并能把信号对应到具体帧。
需 IS_DEV=True（或先 set_replay_folder）才会读视频而非摄像头。

用法：cd kurumi && python test_change_watcher.py
"""
import queue
import time
from collections import deque

import screenshot
from change_watcher import ChangeWatcher
from gamestate import set_gamestate, get_gamestate


def _instrument(q, name):
    """给队列实例的 put 包一层：每次 put 先按当前帧号打印，再真正入队。
    帧号取 len(screenshot.img_q) - 1，即刚抓的这一帧在 img_q 里的下标，
    与 save_img_q 存盘时的文件下标一致。"""
    orig_put = q.put

    def put(item, *args, **kwargs):
        frame = len(screenshot.img_q) - 1
        print(f'[frame {frame:04d}] [{name}] {item}')
        return orig_put(item, *args, **kwargs)

    q.put = put


def run_over_test_data(max_signals=100000):
    # 关掉每帧 imshow，批量跑测试时不弹窗/不刷屏
    screenshot.SHOW_SCREENSHOW = False
    # 用一个足够大的、全新的 img_q，保证从 0 号帧开始不丢帧，帧号 == 存盘下标
    screenshot.img_q = deque(maxlen=1_000_000)

    # gamestate 已在模块加载时由 set_gamestate(_state_3) 设好（含 current_player /
    # player_to_id / player_info 的 kawa_index、melds 等），watcher 的
    # tsumo/dahai/meld 检测直接读它；这里只从中取出手番基准喂给 watcher.reset。
    gs = get_gamestate()
    current_player = gs['current_player']
    player_to_id = gs['player_to_id']

    w = ChangeWatcher()
    w.reset(current_player, player_to_id)

    queues = {'player_change': w.player_q, 'tsumo': w.tsumo_q,
              'dahai': w.dahai_q, 'meld': w.meld_q, 'end': w.end_q}
    # start 前挂钩每个队列的 put，才能捕获 watcher 线程里的每一次入队
    for name, q in queues.items():
        _instrument(q, name)

    w.start()        # watcher 自驱：每轮 get_screenshot 推进游标、并行识别

    # 主线程只负责判定收工（终局或长时间无新信号）；每次 put 已在 watcher 线程打印。
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
            if name == 'end':
                ended = True   # 终局，收工
        if got:
            idle = 0.0
        else:
            # 视频/片段已跑到结尾（VIDEO_END_MS 或真正结束），队列也抽干了 → 立即收工，
            # 不必空等 idle；否则 watcher 会在 dev 下空转往 img_q 灌 False 帧。
            if screenshot._current_frame is False:
                break
            time.sleep(0.05)
            idle += 0.05
            if idle >= 5:      # 5s 无新信号（卡住/其它帧源），兜底收工
                break

    w.stop()


    print(f'\n共消费 {len(events)} 个信号（每次 put 见上方 [frame N] 打印）')
    return events

_state_3 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'last_player': 3, 'last_dahai': '4z', 'dora_markers': ['3m', '4s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 14, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2z', '2z'], 'tile': '2z'}, {'type': 'pon', 'consumed': ['1m', '1m'], 'tile': '1m'}, {'type': 'daiminkan'}], 'riichi': False}, {'kawa_index': 12, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
set_gamestate(_state_3)
if __name__ == '__main__':
    run_over_test_data()
