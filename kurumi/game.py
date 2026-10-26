import warnings
warnings.filterwarnings("ignore")
import json
import time

from kyoku import rec_kyoku_info, check_new_dora_marker, wait_new_kyoku
from gamestate import get_gamestate, init_gamestate, set_gamestate, Phase
from hand import rec_hand
from util import polling, timed
from config import POLLING_INTERVAL, IS_DEV
from pynput import keyboard
from mortal.bot import Bot
from change_watcher import ChangeWatcher
from debug.recorder import get_recorder
import queue

# TODO
# ai print less !
# 听牌提示 认为打牌问题 o
# 打牌太快问题。 !
# 杠 哪个问题
# 窗口最大化
# TODO print 输出到app上，app上更新游戏状态，开始和停止游戏。 停止游戏后没有更新分值悬浮窗状态
# TODO 保证只有app也能很好运行，异常状态保存现场。
# TODO 测试replay
# TODO ctrl + c Traceback (most recent call last):
#   File "C:\game\code\mjai\aiplay\kurumi\mortal\bot.py", line 24, in react
#     if reaction := self.ai.react(eventstr):
#                    ^^^^^^^^^^^^^
# AttributeError: 'NoneType' object has no attribute 'react'
# [SERVER] 收到 Ctrl+C，退出进程
# AttributeError: 'NoneType' object has no attribute 'react'
def print_with_color(text, color = 'green'):
    ts = time.strftime('%H:%M:%S')
    if color == 'green':
        print(f'\033[32m [GAME] {text} \033[0m')
    elif color == 'red':
        print(f"\033[31m [GAME] {text} \033[0m")
    elif color == 'blue':
        print(f"\033[34m [AI] {text} \033[0m")

print_with_color('正在识别牌局信息...')
class Game:
    """流程由 main 独占控制；gamestate 只有 main 写，watcher 只读。

    watcher 对 4 家各自独立识别「下一个牌河格 / 下一个副露位」，识别到就 put 一次，
    被 main 取走后才重新识别。main 不再依赖 active bar 推进手番，而是按座次从各家队列
    取事件：
      Tsumo : 自己等 tsumo_q；他家直接记 '?'
      Dahai : 取 meld_q[p] 的暗杠/加杠，或 dahai_q[p] 的打牌
      Claim : 看别家 meld_q 有无 chi/pon/daiminkan；没有则以「下家打牌 / 下家暗杠加杠 /
              自己摸牌」作为无人鸣牌、轮到下家的证据
    所有事件带 ctx（玩家 + kawa_index + 副露类型序列），与实时 ctx 对不上的视为陈旧丢弃。

    kawa_index 语义：「下一个空位，不含被鸣的牌」。
      - 取走 dahai 事件后立刻 +1（在 notify 之前，避免 watcher 在同一格重复识别）
      - 被别人 chi/pon/大明杠 后 -1
    副露同理：先写进 melds，再 notify。
    """
    def __init__(self, listener = None):
        init_gamestate()
        self.state = get_gamestate()
        self.mjai = []
        self.last_dahai = None
        self.last_player = None
        self.riichi_to_accepted = None
        self.need_open_dora = 0
        self.phase = Phase.StartGame
        self.remaining_tsumo = 70
        if IS_DEV:
            self.bot = None
        else:
            self.bot = Bot()
        self.listener = listener
        # watcher 永远起：dev/replay 下两个读取者各持独立游标读同一帧源，
        # 复刻生产环境的并行取帧，main 流程不区分 dev/生产。
        self.watcher = ChangeWatcher()
        self._end = None       # 已取出的终局事件（hora / ryukyoku），EndKyoku 清空
        self._running = True   # main 循环开关；stop() 置 False 让其退出
        self._hotkey_listener = None
        
    def start_hotkeys(self):
        def on_press(key):
            if key == keyboard.Key.f1:
                print_with_color('按下了F1，保存最近截图', 'red')
                self.stop()
                get_recorder().dump('F1')
        self._hotkey_listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener.start()

    def stop_hotkeys(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    @property
    def phase(self):
        # phase 归属 gamestate，唯一真相源就是 gamestate['phase']；main 负责更新。
        return self.state.get('phase')

    @phase.setter
    def phase(self, value):
        old = self.state.get('phase')
        if old != value:
            get_recorder().log('main', 'phase', old=old, new=value)
        self.state['phase'] = value

    # last_player / last_dahai 同样归属 gamestate：main 更新。
    @property
    def last_player(self):
        return self.state.get('last_player')

    @last_player.setter
    def last_player(self, value):
        self.state['last_player'] = value

    @property
    def last_dahai(self):
        return self.state.get('last_dahai')

    @last_dahai.setter
    def last_dahai(self, value):
        self.state['last_dahai'] = value

    def start_with_state(self, state):
        set_gamestate(state)
        self.watcher.reset(self.state['current_player'], self.state['player_to_id'])
        self.watcher.start()
        self.bot = None


    def start_kyoku(self):
        get_recorder().reset()
        get_recorder().log('main', 'new_kyoku')
        print("Starting new kyoku...")
        # init 
        init_gamestate()
        self.remaining_tsumo = 70
        self.need_open_dora = 0
        self.riichi_to_accepted = None
        self.last_dahai = None
        self.last_player = None
        self._end = None

        state = self.state
        kyoku_info = rec_kyoku_info()
        state['bakaze'] = kyoku_info['bakaze']
        state['kyoku'] = kyoku_info['kyoku']
        state['honba'] = kyoku_info['honba']
        state['kyotaku'] = kyoku_info['kyotaku']
        state['dora_markers'] = [kyoku_info['dora_marker']]

        players = ['self', 'next', 'across', 'prev']
        oya_id = kyoku_info['kyoku'] - 1
        oya_index = players.index(kyoku_info['oya'])
        
        state['oya'] = oya_id
        state['current_player'] = oya_id

        player_to_id = {
            player: (oya_id - oya_index + i) % 4
            for i, player in enumerate(players)
        }

        position = [''] * 4
        for key, idx in player_to_id.items():
            position[idx] = key

        state['player_to_id'] = player_to_id
        state['position'] = position
        state['my_id'] = player_to_id['self']

        # 每局一条监视线程：设手番基准后拉起，终局中断时线程自退
        self.watcher.reset(oya_id, player_to_id)
        self.watcher.start()

        id_to_score = {
            player_to_id[player]: score
            for player, score in zip(players, kyoku_info['scores'])
        }
        state['scores'] = [id_to_score[i] for i in state['players']]

        hands = rec_hand()
        print('hand: ', hands)
        tehais = [['?']* 13, ['?']* 13, ['?']* 13, ['?']* 13]
        tehais[state['my_id']] = hands 
        self.notify({
            'type': 'start_kyoku',
            'bakaze': state['bakaze'],
            'kyoku': state['kyoku'],
            'honba': state['honba'],
            'kyotaku': state['kyotaku'],
            'dora_marker': state['dora_markers'][0],
            'oya': state['oya'],
            'scores': state['scores'],
            'tehais': tehais
        })
        print("update gamestate: ", state)

    def tsumo(self, player, tile):
        print_with_color(f'玩家 {player} 摸牌 < {tile} >')
        self.notify({
            'type': 'tsumo',
            'actor': player,
            'pai': tile,
        })
    
    def dahai(self, player, tile, tsumogiri, riichi):
        # 先推进牌河位置再 notify：消费与推进之间不留空窗，watcher 不会在同一格重复识别。
        self.state['player_info'][player]['kawa_index'] += 1
        # 自己打牌后，摸牌事件作废（watcher 在摸牌仍显示时可能重复 put 同 ctx 的摸牌）
        if player == self.state['my_id']:
            self._drain(self.watcher.tsumo_q)

        self.last_dahai = tile
        self.last_player = player
        
        # riichi 要排除已经立直的，只是因为被鸣牌而重新检测到riichi
        if riichi and not self.state['player_info'][player]['riichi']:
            print_with_color(f'玩家 {player} 立直')
            self.notify({ 'type': 'reach', 'actor': player })
            self.riichi_to_accepted = player
            self.state['player_info'][player]['riichi'] = True

        print_with_color(f'玩家 {player} {"打" if not tsumogiri else "摸切"} {tile}')
        self.notify({
            'type': 'dahai',
            'actor': player,
            'pai': tile,
            'tsumogiri': tsumogiri
        })
        return

    def _unclaim_discard(self):
        """last_player 刚打出的牌被鸣走：牌河位置回退，不含被鸣的牌。"""
        lp = self.last_player
        self.state['player_info'][lp]['kawa_index'] -= 1
        # 自己的牌被鸣：kawa_index 回退后 ctx 会回到打牌前的值，
        # 清掉可能残留的旧摸牌事件，避免它被下一轮摸牌误当成新摸牌。
        if lp == self.state['my_id']:
            self._drain(self.watcher.tsumo_q)
    
    def claim(self, player, meld):
        """副露：先更新 gamestate（melds / kawa_index），再 notify。"""
        player_melds = self.state['player_info'][player]['melds']
        type = meld['type']

        if type == 'chi' or type == 'pon':
            print_with_color(f'玩家 {player} {type} < {meld["consumed"]} >')
            player_melds.append({
                'type': type,
                'consumed': meld['consumed'],
                'tile': self.last_dahai
            })
            self._unclaim_discard()
            self.notify({
                'type': type,
                'consumed': meld['consumed'],
                'pai': self.last_dahai,
                'actor': player,
                'target': self.last_player
            })
        elif type == 'daiminkan':
            num, suit = self.last_dahai
            if num == '5' and self.last_dahai != '5z':
                consumed = [self.last_dahai] * 2 + ['0' + suit]
            elif num == '0':
                consumed = ['5' + suit] * 3
            else:
                consumed = [self.last_dahai] * 3
                
            print_with_color(f'player {player} {type} < {consumed} >')
            player_melds.append({ 'type': 'daiminkan' })
            self._unclaim_discard()
            self.notify({
                'type': type,
                'actor': player,
                'target': self.last_player,
                'pai': self.last_dahai,
                'consumed': consumed,
            })

        elif type == 'ankan':
            tile = meld['tile']
            num, suit = tile
            if num == '5' and tile != '5z':
                consumed = [tile] * 3 + ['0' + suit]
            else:
                consumed = [tile] * 4
            print_with_color(f'player {player} {type} < {consumed} >')
            player_melds.append({ 'type': 'ankan' })
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
            })
        elif type == 'kakan':
            consumed = [meld['tile'], *meld['consumed']]
            num, suit = meld['tile']
            if num == '5' and suit != 'z':
                if consumed[1][0] == '5' and consumed[2][0] == '5':
                    pai = '0' + suit
                else:
                    pai = '5' + suit
            else:
                pai = consumed[1]
            
            print_with_color(f'player {player} {type} < {pai} >')
            # 更新meld
            for _meld in player_melds:
                if _meld['type'] == 'pon' and _meld['tile'] == meld['tile']:
                    _meld['type'] = 'kakan'
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
                'pai': pai
            })

    def open_dora(self):
        dora_marker = polling(check_new_dora_marker, POLLING_INTERVAL, timeout = 5)
        self.state['dora_markers'].append(dora_marker)
        print_with_color(f'新宝牌指示牌 < {dora_marker} >')
        self.notify({
            'type': 'dora',
            'dora_marker': dora_marker
        })
        self.need_open_dora = False

    # ------------------------------------------------------------ 队列工具
    @staticmethod
    def _drain(q):
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return

    def _peek(self, q, pid):
        """看 pid 的队首事件（不取）；ctx 与实时不符的陈旧事件由 watcher.peek 就地丢弃。"""
        return self.watcher.peek(q, self.watcher.ctx_of(pid))

    def _take(self, q, pid, name):
        """取走 pid 的队首事件。调用方必须随即推进 gamestate（kawa_index / melds），
        因为取走后 watcher 才会重新识别该项。"""
        item = self.watcher.take(q, self.watcher.ctx_of(pid))
        if item is not None:
            get_recorder().log('main', 'consume', q=name, item=item)
        return item

    def _poll_end(self):
        """终局事件取出后存入 self._end，之后每个等待点都能看到。"""
        if self._end is None:
            try:
                self._end = self.watcher.end_q.get_nowait()
                get_recorder().log('main', 'consume', q='end_q', item=self._end)
            except queue.Empty:
                pass

    def _goto_end(self):
        """有终局事件则切到 Hora / Ryukyoku，返回 True。"""
        if self._end is None:
            return False
        if self._end['type'] == 'hora':
            self.phase = Phase.Hora
            return True
        if self._end['type'] == 'ryukyoku':
            self.phase = Phase.Ryukyoku
            return True
        return False

    def _finish_discard(self):
        """一张牌打出且确认无人 荣和/抢 之后的收尾：开新宝牌、立直成立。
        （kawa_index 已在 dahai() 里推进，不在这里。）"""
        if self.need_open_dora:
            self.open_dora()

        if self.riichi_to_accepted is not None:
            print('reach_accept')
            self.notify({ 'type': 'reach_accepted', 'actor': self.riichi_to_accepted })
            self.riichi_to_accepted = None

    def _find_claim(self, p):
        """p 刚打牌，找别家的 chi/pon/daiminkan。返回 (q, meld) 或 None。"""
        w = self.watcher
        for off in (1, 2, 3):
            q = (p + off) % 4
            m = w.peek(w.meld_q[q], w.ctx_of(q))
            if m is None or m['type'] not in ('chi', 'pon', 'daiminkan'):
                continue
            if m['type'] == 'chi' and q != (p + 1) % 4:
                raise RuntimeError(
                    f'玩家 {q} 识别到吃，但打牌者 {p} 不是其上家，副露识别有误')
            return q, m
        return None

    def _next_actor_evidence(self, p):
        """p 打牌后无人鸣牌，下家 (p+1) 已行动的证据：
        下家打牌 / 下家暗杠或加杠 / 下家是自己且已摸牌。"""
        w = self.watcher
        q = (p + 1) % 4
        ctx = w.ctx_of(q)
        if w.peek(w.dahai_q[q], ctx) is not None:
            return True
        m = w.peek(w.meld_q[q], ctx)
        if m is not None and m['type'] in ('ankan', 'kakan'):
            return True
        if q == self.state['my_id'] and w.peek(w.tsumo_q, ctx) is not None:
            return True
        return False

    def main(self):
        INTERVAL_TIME = 0.1
        state = self.state
        w = self.watcher

        # 所有识别都在 watcher 线程并行，main 只在各 phase 按需从队列取结果，自身不做任何识别。
        # 手番流转不再依赖 active bar：由「各家打牌 / 副露 / 自己摸牌」事件按座次推导。
        while self._running:
            # watcher 线程崩溃时 main 不能静默卡死
            if w.error is not None:
                raise RuntimeError(f'watcher 线程异常: {w.error!r}') from w.error

            # 终局事件优先级最高：对局中的任何阶段一旦出现，直接收尾，
            # 队列里残留的事件作废（本局结束，不再需要）。
            # 仅在对局阶段判断，避免在 Hora/EndKyoku 等收尾阶段重复触发。
            self._poll_end()
            if self.phase in (Phase.Tsumo, Phase.Dahai, Phase.Claim) and self._goto_end():
                continue

            player = state['current_player']

            if self.phase == Phase.Tsumo:
                if player == state['my_id']:
                    ev = self._take(w.tsumo_q, player, 'tsumo_q')
                    if ev is None:
                        time.sleep(INTERVAL_TIME)
                        continue
                    tile = ev['tile']
                else:
                    tile = '?'

                self.tsumo(player, tile)
                self.phase = Phase.Dahai

            elif self.phase == Phase.Dahai:
                # 暗杠 / 加杠：摸牌后、打牌前
                m = self._peek(w.meld_q[player], player)
                if m is not None and m['type'] in ('ankan', 'kakan'):
                    m = self._take(w.meld_q[player], player, f'meld_q{player}')
                    self.claim(player, m)
                    if m['type'] == 'ankan':
                        if self.need_open_dora:
                            self.open_dora()
                        self.open_dora()
                    else:
                        if self.need_open_dora:
                            self.open_dora()
                        self.need_open_dora = True
                    self.phase = Phase.Tsumo   # 岭上摸牌
                    continue

                d = self._take(w.dahai_q[player], player, f'dahai_q{player}')
                if d is None:
                    time.sleep(INTERVAL_TIME)
                    continue

                self.dahai(player, d['tile'], d['tsumogiri'], d['riichi'])
                self.phase = Phase.Claim

            elif self.phase == Phase.Claim:
                p = self.last_player

                # 1. 别家鸣牌（chi / pon / daiminkan）
                found = self._find_claim(p)
                if found is not None:
                    q, m = found
                    self._finish_discard()           # 开新宝牌、立直成立，先于鸣牌通知
                    m = self._take(w.meld_q[q], q, f'meld_q{q}')
                    self.claim(q, m)                 # 内部回退 p 的 kawa_index
                    state['current_player'] = q
                    if m['type'] == 'daiminkan':
                        self.need_open_dora = True
                        self.phase = Phase.Tsumo     # 岭上摸牌
                    else:
                        self.phase = Phase.Dahai
                    continue

                # 2. 无人鸣牌：下家已行动，轮到下家
                if self._next_actor_evidence(p):
                    self._finish_discard()
                    state['current_player'] = (p + 1) % 4
                    self.phase = Phase.Tsumo
                    continue

                time.sleep(INTERVAL_TIME)

            elif self.phase == Phase.StartKyoku:
                self.start_kyoku()
                self.phase = Phase.Tsumo

            elif self.phase == Phase.Hora:
                # TODO 最后一张ron牌难以被识别
                print_with_color('和了')
                # self.notify({
                #     'type': 'hora'
                # })
                self.watcher.stop()
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.Ryukyoku:
                # TODO 九种九牌流局后，太快重开了，wait new kyoku导致识别到流局时的状态为下一局开始了
                print_with_color('流局')
                # self.notify({
                #     'type': 'ryukyoku'
                # })

                self.watcher.stop()
                time.sleep(7)
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.EndKyoku:
                self._end = None
                self.watcher.stop()
                self.notify({
                    'type': 'end_kyoku'
                })
                init_gamestate()
                is_new_kyoku = wait_new_kyoku()
                if is_new_kyoku:
                        self.phase = Phase.StartKyoku
                else:
                    self.phase = Phase.EndGame
               
            elif self.phase == Phase.StartGame:
                wait_new_kyoku()
                self.phase = Phase.StartKyoku

            elif self.phase == Phase.EndGame:
                print_with_color('游戏结束')
                self.notify({
                    'type': 'end_game'
                })
                self.print_mjai()
                break

    def notify(self, message):
        
        self.mjai.append(message)
        get_recorder().log('main', 'mjai', msg=message)

        if self.listener is not None:
            self.listener({ 'type': 'mjai', 'data': message })

        if self.bot is None:
            return
        
        with timed('bot.react(AI)'):
            if message['type'] == 'start_kyoku':
                self.bot.start(self.state['my_id'])
                react = self.bot.react(message)
            elif message['type'] == 'end_kyoku':
                react = self.bot.react(message)
                self.bot.end()
            else:
                react = self.bot.react(message)
        if 'error' in react:
            raise RuntimeError('AI React Error', react['error'])
        
        if self.listener is not None:
            self.listener({ 'type': 'ai', 'data': react })

        print_with_color(react, 'blue')
        return

    def print_mjai(self):
        print('^^^^^^^^^^- mjai -^^^^^^^^^^')
        for e in self.mjai:
            str = json.dumps(e)
            print(str)

    def start(self):
        self.start_hotkeys()
        try:
            self.main()
        except Exception as e:
            self.watcher.stop()      # 先停 watcher，再存图
            get_recorder().log_exception('main', e)
            get_recorder().dump('exception')
            print(self.state)
            raise

        finally:
            self.watcher.stop()
            self.stop_hotkeys()
    
    def stop(self):
        """停止游戏：置停止标志让 main 循环下一轮退出，并回收 watcher 线程。"""
        self._running = False
        self.watcher.stop()

_state_3 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'last_player': 0, 'last_dahai': '4z', 'dora_markers': ['3m', '4s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 14, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2z', '2z'], 'tile': '2z'}, {'type': 'pon', 'consumed': ['1m', '1m'], 'tile': '1m'}, {'type': 'daiminkan'}], 'riichi': False}, {'kawa_index': 12, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
_state_1 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 2, 'dora_markers': ['4s'], 'scores': [23000, 24500, 24500, 28000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 1, 'player_info': [{'kawa_index': 7, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 8, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 8, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 8, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
_state_2 = {'honba': 2, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 3, 'dora_markers': ['1p'], 'scores': [43000, 33900, 19300, 3800], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 2, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 2, 'player_info': [{'kawa_index': 1, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 1, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 1, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 1, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
if __name__ == "__main__":
    game = None
    try:
        game = Game()
        # game.start_with_state(_state_2)
        # game.phase = Phase.Tsumo
        game.start()
    except Exception as e:
        print_with_color('游戏中止，打印中止时的GAME STATE', 'red')
        print(game.state)
        raise e
    except KeyboardInterrupt:
        print_with_color('游戏中止，打印中止时的GAME STATE', 'red')
        print(game.state)
    finally:
        # 无论正常退出、异常还是 Ctrl+C，都回收 watcher 线程
        if game is not None:
            game.watcher.stop()
