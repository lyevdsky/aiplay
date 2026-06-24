import warnings
warnings.filterwarnings("ignore")
import asyncio
import json
import time

from screenshot import get_screenshot, save_img_q
from kyoku import rec_kyoku_info, check_new_dora_marker, wait_new_kyoku
from gamestate import get_gamestate, init_gamestate, set_gamestate
from hand import rec_hand, check_tsumo, rec_tsumo
from kawa import check_dahai, check_dahai_claimed
from meld import check_new_meld, check_kan
from util import polling
from config import POLLING_INTERVAL
from enum import Enum
from pynput import keyboard
from mortal.bot import Bot
from kurumi.mortal.conv import format_output
from change_watcher import ChangeWatcher
from hora import check_interrupt
import queue

class Phase(Enum):
    StartKyoku = 0
    Dahai = 1
    Tsumo = 2
    Claim = 3
    Hora = 4
    Ryukyoku = 5
    EndKyoku = 6
    EndGame = 7
    StartGame = 8

# TODO
# ai print less !
# 听牌提示 认为打牌问题 o
# 打牌太快问题。 !
# 杠 哪个问题
# 窗口最大化

def print_with_color(text, color = 'green'):
    if color == 'green':
        print(f'\033[32m [GAME] {text} \033[0m')
    elif color == 'red':
        print(f"\033[31m [GAME] {text} \033[0m")
    elif color == 'blue':
        print(f"\033[34m [AI] {text} \033[0m")

print_with_color('正在识别牌局信息...')
class Game:
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
        self.bot = Bot()
        self.listener = listener
        # watcher 永远起：dev/replay 下两个读取者各持独立游标读同一帧源，
        # 复刻生产环境的并行取帧，main 流程不区分 dev/生产。
        self.watcher = ChangeWatcher()

    def start_with_state(self, state):
        set_gamestate(state)
        self.bot = None

    def start_kyoku(self):
        print("Starting new kyoku...")
        # init 
        init_gamestate()
        self.remaining_tsumo = 70
        self.need_open_dora = 0
        self.riichi_to_accepted = None
        self.last_dahai = None
        self.last_player = None

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
    
    def claim(self, player, meld):
        player_melds = self.state['player_info'][player]['melds']
        type = meld['type']

        if type == 'chi' or type == 'pon':
            print_with_color(f'玩家 {player} {type} < {meld["consumed"]} >')
            self.notify({
                'type': type,
                'consumed': meld['consumed'],
                'pai': self.last_dahai,
                'actor': player,
                'target': self.last_player
            })
            player_melds.append({
                'type': type,
                'consumed': meld['consumed'],
                'tile': self.last_dahai
            })
        elif type == 'daiminkan':
            num, suit = self.last_dahai
            if num == '5':
                consumed = [self.last_dahai] * 2 + ['0' + suit]
            elif num == '0':
                consumed = ['5' + suit] * 3
            else:
                consumed = [self.last_dahai] * 3
            self.notify({
                'type': type,
                'actor': player,
                'target': self.last_player,
                'pai': self.last_dahai,
                'consumed': consumed,
            })
            player_melds.append({ 'type': 'daiminkan' })

            print_with_color(f'player {player} {type} < {consumed} >')
        elif type == 'ankan':
            tile = meld['tile']
            num, suit = tile
            if num == '5':
                consumed = [tile] * 3 + ['0' + suit]
            else:
                consumed = [tile] * 4
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
            })
            print_with_color(f'player {player} {type} < {consumed} >')
            player_melds.append({ 'type': 'ankan' })
        elif type == 'kakan':
            # 注意 加杠返回的是之前碰的副露内容，
            consumed = [meld['tile'], *meld['consumed']]
            num, suit = meld['tile']
            if num == '5':
                if consumed[1][0] == '5' and consumed[2][0] == '5':
                    pai = '0' + suit
                else:
                    pai = '5' + suit
            else:
                pai = consumed[1]
            
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
                'pai': pai
            })
            meld['type'] = 'kakan'
            print_with_color(f'player {player} {type} < {pai} >')

    def open_dora(self):
        dora_marker = polling(check_new_dora_marker, POLLING_INTERVAL, timeout = 5)
        self.state['dora_markers'].append(dora_marker)
        print_with_color(f'新宝牌指示牌 < {dora_marker} >')
        self.notify({
            'type': 'dora',
            'dora_marker': dora_marker
        })
        self.need_open_dora = False

    def main(self):
        state = self.state

        # 监视线程每局由 start_kyoku 拉起（main 在终局调用 stop 回收），此处不再统一启动

        # Claim 阶段消费下一个时序信号：阻塞等 watcher 的 player_change，
        # 同时自己轮询终局中断（watcher 已不产中断，且此处可能一直等不到
        # 下一个 player_change——比如这张牌被荣和 / 这局荒牌流局）。
        # 带超时轮询，否则主线程会卡在 Queue 的 C 级锁里，Ctrl+C 无法生效。
        def wait_signal():
            while True:
                try:
                    return self.watcher.q.get(timeout=POLLING_INTERVAL)
                except queue.Empty:
                    pass
                # check_interrupt：非中断立即返回 None；已进入中断则阻塞到分辨出结果
                interrupt = check_interrupt()
                if interrupt is not None:
                    return {'type': interrupt}

        # check current_player kakan ankan dahai hora
        def check_dahai_phase():
            player = state['current_player']

            # 终局中断检测移回主流程：check_interrupt 一旦确认进入中断动画，
            # 就阻塞等到分辨出 hora / ryukyoku 再返回，期间不再认牌，
            # 避免吃碰杠 / 终局动画被误识别成打牌（见 hora.py 注释）。
            interrupt = check_interrupt()
            if interrupt is not None:
                return interrupt

            meld = check_kan()
            if meld is not None:
                self.claim(player, meld)
                return meld['type']

            res = check_dahai()
            if res is not None:
                tile, tsumogiri, riichi = res
                self.dahai(player, tile, tsumogiri, riichi)
                return 'dahai'

            return None


        while True:
            player = state['current_player']

            if self.phase == Phase.Tsumo:
                if player == state['my_id']:
                    tile = polling(check_tsumo, POLLING_INTERVAL, timeout = 10)
                else:
                    tile = '?'

                self.tsumo(player, tile)
                self.phase = Phase.Dahai

            elif self.phase == Phase.Dahai:
                action = polling(check_dahai_phase, POLLING_INTERVAL, timeout=30)
                if action == 'dahai':
                    if self.need_open_dora:
                        self.open_dora()

                    self.phase = Phase.Claim
                elif action == 'hora':
                    self.phase = Phase.Hora
                elif action == 'ankan':
                    if self.need_open_dora:
                        self.open_dora()
                    self.open_dora()
                    self.phase = Phase.Tsumo
                elif action == 'kakan':
                    if self.need_open_dora:
                        self.open_dora()
                    self.need_open_dora = True
                    self.phase = Phase.Tsumo

            elif self.phase == Phase.Claim:
                # 从队列消费时序信号：active bar 的亮灭转换由后台线程全程
                # 盯着、转换即入队，不再受识别快慢拖累。
                msg = wait_signal()
                if msg['type'] == 'hora':
                    self.phase = Phase.Hora
                    continue
                elif msg['type'] == 'ryukyoku':
                    self.phase = Phase.Ryukyoku
                    continue

                player = msg['pid']
                print_with_color(f'切换至玩家 {player}')

                if self.need_open_dora:
                    self.open_dora()

                if self.riichi_to_accepted is not None:
                    print('reach_accept')
                    self.notify({ 'type': 'reach_accepted', 'actor': self.riichi_to_accepted })
                    self.riichi_to_accepted = None
                    # time sleep 是为了避免立直时放立直棒的手，挡住已打牌，错判鸣牌。
                    time.sleep(0.5)
                    # TODO 
#                 change_watcher: player change to  1
#  [GAME] 切换至玩家 1 
#  [GAME] 玩家 1 摸牌 < ? > 
#  [AI] {'type': 'none'} 
#  [GAME] 玩家 1 pon < ['5m', '0m'] > 
#  6m识别成9m了，kyo.mp4 8:46
#  [GAME] 玩家 0 摸牌 < 6m > 
#  [AI] {'type': 'dahai', 'actor': 0, 'pai': '6m', 'tsumogiri': True, 'meta': {'q_values': [0.0114046335, -3.751009, -3.6414447, -0.08666313, -6.6993093, -6.6142178, -7.7626953, -7.808297, -7.764924, -7.632497, -7.5305443], 'mask_bits': 34374205856, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 50863600, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '6m', 'q_value': 0.0114046335}, {'label': '6p', 'q_value': -0.08666313}, {'label': '9m', 'q_value': -3.6414447}, {'label': '8m', 'q_value': -3.751009}, {'label': '1s', 'q_value': -6.6142178}, {'label': '7p', 'q_value': -6.6993093}, {'label': '0p', 'q_value': -7.5305443}, {'label': '6s', 'q_value': -7.632497}, {'label': '2s', 'q_value': -7.7626953}, {'label': '5s', 'q_value': -7.764924}, {'label': '3s', 'q_value': -7.808297}]} 
# change_watcher: player change to  1
#  [GAME] 玩家 0 打 9m 

# TODO 4p被识别成摸切5z kyo 8:47 并非识别错误，而是不知道什么原因，导致main里的循环过了很多帧，导致跳了一巡
#  [GAME] 玩家 1 摸牌 < ? > 
#  [AI] {'type': 'none'} 
# 误检测为z5 0.35774946921443734
#  [GAME] 玩家 1 摸切 5z 
#  [AI] {'type': 'none'} 
#  [GAME] 切换至玩家 2 
# change_watcher: player change to  3
#  [GAME] 玩家 2 摸牌 < ? > 
#  [AI] {'type': 'none'} 
#  [GAME] 玩家 2 chi < ['3p', '5p'] > 
# TODO 没有清空上一局残留的watcher.q change_watcher: player change to  0
                claimed = check_dahai_claimed()

                state['current_player'] = player

                if claimed:
                    print_with_color(f'玩家 {player} 鸣牌')
                    meld = check_new_meld()
                    self.claim(player, meld)
                    if meld['type'] == 'daiminkan':
                        self.need_open_dora = True
                        self.phase = Phase.Tsumo
                    else:
                        self.phase = Phase.Dahai
                else:
                    if (self.last_player + 1) % 4 != player:
                        raise RuntimeError('没有鸣牌的情况下并没有正确轮到下一位玩家')
                    self.state['player_info'][self.last_player]['kawa_index'] += 1
                    self.phase = Phase.Tsumo

            elif self.phase == Phase.StartKyoku:
                self.start_kyoku()
                self.phase = Phase.Tsumo

            elif self.phase == Phase.Hora:
                print_with_color('和了')
                self.watcher.stop()
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.Ryukyoku:
                print_with_color('流局')
                self.watcher.stop()
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.EndKyoku:
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
                self.print_mjai()
                break
    
    def notify(self, message):
        self.mjai.append(message)

        if self.listener is not None:
            self.listener({ 'type': 'mjai', 'data': message })

        if self.bot is None:
            return
        
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

def on_press(key):
    if key == keyboard.Key.f1:
        print_with_color('按下了F1，保存最近截图', 'red')
        # 这里可以放置你的 F1 功能逻辑
        save_img_q()

listener = keyboard.Listener(on_press=on_press)
listener.start()

if __name__ == "__main__":
    game = None
    try:
        game = Game()
        # game.start_with_state(_state_full_5)
        # game.phase = Phase.Dahai
        game.main()
    except Exception as e:
        game.watcher.save_img_q()
        save_img_q()
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
