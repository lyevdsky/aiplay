import warnings
warnings.filterwarnings("ignore")
import asyncio
import json
import time

from screenshot import get_screenshot, save_img_q
from kyoku import rec_kyoku_info, check_player_change, check_new_dora_marker, wait_new_kyoku
from gamestate import get_gamestate, init_gamestate, set_gamestate
from hand import rec_hand, check_tsumo, rec_tsumo
from kawa import check_dahai, check_dahai_claimed
from meld import check_new_meld, check_kan
from hora import check_interrupt
from util import polling
from config import POLLING_INTERVAL
from enum import Enum
from pynput import keyboard
from mortal.bot import Bot
from kurumi.mortal.conv import format_output

class Phase(Enum):
    StartKyoku = 0
    Dahai = 1
    Tsumo = 2
    Claim = 3
    Hora = 4
    EndKyoku = 5
    EndGame = 6
    StartGame = 7

# TODO
# 流局 判断 x
# settle
# ai reach dahai 
# ai print less !
# new kyoku gameloop !!!!!!!!!!!
# 听牌提示 认为打牌问题 o
# 打牌太快问题。 !
# ui -
# 杠 哪个问题
# ai none 时有可能是鸣牌跳过  x
# ai result 还要展示概率 x
# 自摸 x
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

    def start_with_state(self, state):
        set_gamestate(state)
        self.bot = None

    def start_kyoku(self):
        print("Starting new kyoku...")
        init_gamestate()
        state = self.state
        kyoku_info = rec_kyoku_info()
        print("Kyoku info:", kyoku_info)
        if kyoku_info['bakaze'] == 'E':
            kyoku = kyoku_info['kyokunum']
        elif kyoku_info['bakaze'] == 'S':
            kyoku = kyoku_info['kyokunum'] + 4
        elif kyoku_info['bakaze'] == 'W':
            kyoku = kyoku_info['kyokunum'] + 8
        state['kyoku'] = kyoku
        state['honba'] = kyoku_info['honba']
        state['kyotaku'] = kyoku_info['kyotaku']
        state['dora_markers'] = [kyoku_info['dora_marker']]

        players = ['self', 'next', 'across', 'prev']
        oya_id = kyoku_info['kyokunum'] - 1
        oya_index = players.index(kyoku_info['oya'])

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

        id_to_score = {
            player_to_id[player]: score
            for player, score in zip(players, kyoku_info['scores'])
        }
        state['scores'] = [id_to_score[i] for i in state['players']]

        hands = rec_hand()
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
        #current player dahai
        self.last_dahai = tile
        self.last_player = player
        
        print('player ', player, ' dahai ', tile, tsumogiri, riichi)
        # riichi 要排除已经立直的，只是因为被鸣牌而重新检测到riichi
        if riichi and not self.state['player_info'][player]['riichi']:
            self.notify({ 'type': 'reach', 'actor': player })
            self.riichi_to_accepted = player
            self.state['player_info'][player]['riichi'] = True

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

        # check current_player kakan ankan dahai hora
        def check_dahai_phase():
            player = state['current_player']

            interrupt = check_interrupt()
            if interrupt:
                return interrupt
            
            meld = check_kan()
            if meld is not None:
                self.claim(player, meld)
                return meld['type']

            res = check_dahai()
            if res is not None:
                tile, tsumogiri, riichi = res
                print_with_color(f'玩家 {player} 打 {tile}')
                self.dahai(player, tile, tsumogiri, riichi)
                return 'dahai'

            return None
        
        def check_claim_phase():
            interrupt = check_interrupt()
            if interrupt:
                return interrupt

            player = check_player_change()
            if player is not None:
                # print_with_color(f'切换至玩家 {player}')
                return player
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
                # player change / hora
                playerOrInterrupt = polling(check_claim_phase, POLLING_INTERVAL, timeout=30)
                if playerOrInterrupt == 'hora':
                    self.phase = Phase.Hora
                    continue
                else:
                    player = playerOrInterrupt

                if self.need_open_dora:
                    self.open_dora()

                if self.riichi_to_accepted is not None:
                    self.notify({ 'type': 'reach_accepted', 'actor': self.riichi_to_accepted })
                    self.riichi_to_accepted = None

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
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.EndKyoku:
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
        elif message['type'] == 'end_kyoku':
            self.bot.end()

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
_state_full_3 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'dora_markers': ['5s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 6, 'riichi_index': None, 'melds': [{'type': 'chi'}], 'riichi': False}, {'kawa_index': 6, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 5, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 5, 'riichi': False, 'riichi_index': None, 'melds': [{"type": 'chi'}]}], 'my_id': 0}
_state_full_2 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'dora_markers': ['5s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 2, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 2, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 2, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 2, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
_state_full_1 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 2, 'dora_markers': ['5m'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['prev', 'self', 'next', 'across'], 'current_player': 3, 'player_to_id': {'self': 1, 'next': 2, 'across': 3, 'prev': 0}, 'oya': 0, 'player_info': [{'kawa_index': 7, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 8, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 7, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 7, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 1}
# 2:20 = 140000
# _state3 = {'honba': '', 'kyotaku': '', 'bakaze': 'E', 'kyoku': 4, 'dora_markers': ['1p'], 'scores': ['11300', '21000', '7', '33700'], 'players': [0, 1, 2, 3], 'position': ['across', 'prev', 'self', 'next'], 'current_player': 3, 'player_to_id': {'self': 2, 'next': 3, 'across': 0, 'prev': 1}, 'oya': 0, 'player_info': [{'kawa_index': 13, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 12, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 13, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2p', '2p'], 'tile': '2p'}, {'type': 'ankan'}]}, {'kawa_index': 14, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['0m', '5m'], 'tile': '5m'}, {'type': 'ankan'}, {'type': 'pon', 'consumed': ['8p', '8p'], 'tile': '8p'}]}], 'my_id': 2}
# _state2 = {'honba': '', 'kyotaku': '', 'bakaze': 'E', 'kyoku': 4, 'dora_markers': ['1p'], 'scores': ['11300', '21000', '7', '33700'], 'players': [0, 1, 2, 3], 'position': ['across', 'prev', 'self', 'next'], 'current_player': 0, 'player_to_id': {'self': 2, 'next': 3, 'across': 0, 'prev': 1}, 'oya': 0, 'player_info': [{'kawa_index': 12, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 11, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 12, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2p', '2p'], 'tile': '2p'}, {'type': 'ankan'}]}, {'kawa_index': 14, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['0m', '5m'], 'tile': '5m'}, {'type': 'ankan'}, {'type': 'pon', 'consumed': ['8p', '8p'], 'tile': '8p'}]}], 'my_id': 2}
# _state = {'honba': '', 'kyotaku': '', 'bakaze': 'E', 'kyoku': 4, 'dora_markers': ['1p'], 'scores': ['11300', '21000', '7', '33700'], 'players': [0, 1, 2, 3], 'position': ['across', 'prev', 'self', 'next'], 'current_player': 2, 'player_to_id': {'self': 2, 'next': 3, 'across': 0, 'prev': 1}, 'oya': 0, 'player_info': [{'kawa_index': 4, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 4, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 3, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2p', '2p'], 'tile': '2p'}]}, {'kawa_index': 4, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['0m', '5m'], 'tile': '5m'}]}], 'my_id': 2}
if __name__ == "__main__":
    try:
        game = Game()
        # game.start_with_state(_state_full_3)
        # game.phase = Phase.Tsumo
        game.main()
    except Exception as e:
        save_img_q()
        print_with_color('游戏中止，打印中止时的GAME STATE', 'red')
        print(game.state)
        raise e
    except KeyboardInterrupt:
        print_with_color('游戏中止，打印中止时的GAME STATE', 'red')
        print(game.state)
