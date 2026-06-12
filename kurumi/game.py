import asyncio
import json
import time

from screenshot import get_screenshot, save_img_q
from kyoku import rec_kyoku_info, check_player_change, check_new_dora
# from meld import get_new_meld, check_kakan
from gamestate import get_gamestate, init_gamestate
from hand import rec_hand, check_tsumo
from kawa import check_dahai, check_dahai_claimed
from meld import check_new_meld, check_kan
from hora import check_hora
from util import polling
from config import POLLING_INTERVAL
from enum import Enum

class Phase(Enum):
    Dahai = 1
    Tsumo = 2
    Claim = 3
    Hora = 4

# next meld 不断增加
# yolo 0m

def print_with_color(text, color = 'green'):
    if color == 'green':
        print(f'\033[32m [GAME] {text} \033[0m')
    elif color == 'red':
        print(f"\033[31m [GAME] {text} \033[0m")

print_with_color('正在识别牌局信息...')
class Game:
    def __init__(self):
        init_gamestate()
        self.state = get_gamestate()
        self.my_id = 0
        self.mjai = []
        self.last_dahai = None
        self.last_player = None
        self.riichi_to_accepted = None
        self.need_open_dora = 0
        self.phase = Phase.Tsumo
        self.remaining_tsumo = 70
        
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
        self.my_id = state['my_id']

        id_to_score = {
            player_to_id[player]: score
            for player, score in zip(players, kyoku_info['scores'])
        }
        state['scores'] = [id_to_score[i] for i in state['players']]

        hands = rec_hand()
        tehais = [['?']* 13, ['?']* 13, ['?']* 13, ['?']* 13]
        tehais[self.my_id] = hands 
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
            'tile': tile,
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
            'tsumogiri': tsumogiri,
            'riichi': riichi
        })
        return
    
    def claim(self, player, meld):
        player_melds = self.state['player_info'][player]['melds']
        type = meld['type']

        if type == 'chi' or type == 'pon':
            self.notify({
                'type': type,
                'consumed': meld['consumed'],
                'pai': self.last_dahai,
                'actor': player,
                'target': self.last_player
            })
            print_with_color(f'玩家 {player} {type} < {meld["consumed"]} >')
            player_melds.append({
                'type': type,
                'consumed': meld['consumed'],
                'tile': self.last_dahai
            })
        elif type == 'daiminkan':
            num, suit = self.last_dahai
            if num == 5:
                consumed = ([self.last_dahai] * 2).append('0' + suit)
            elif num == 0:
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
            if num == 5:
                consumed = ([tile] * 3).append('0' + suit)
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
                if consumed[1][0] == '5' and consumed[2][0] == 5:
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
        dora_marker = polling(check_new_dora, POLLING_INTERVAL, timeout = 5)
        self.notify({
            'type': 'dora',
            'dora_marker': dora_marker
        })
        self.need_open_dora = False

    async def main(self):
        # check current_player kakan ankan dahai hora
        def check_dahai_phase():
            player = state['current_player']

            hora = check_hora()
            if hora:
                return 'hora'
            
            meld = check_kan()
            if meld is not None:
                self.claim(player, meld)
                return 'kan'

            # 自摸check
            res = check_dahai()
            if res is not None:
                tile, tsumogiri, riichi = res
                print_with_color(f'玩家 {player} 打 {tile}')
                self.dahai(player, tile, tsumogiri, riichi)
                return 'dahai'

            return None
        
        def check_claim_phase():
            hora = check_hora()
            if hora:
                return 'hora'

            player = check_player_change()
            if player is not None:
                print_with_color(f'切换至玩家 {player}')
                return player
            return None
        
        state = self.state
        self.start_kyoku()
        while True:
            player = state['current_player']
            if self.phase == Phase.Tsumo:
                if player == self.my_id:
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
                playerOrHora = polling(check_claim_phase, POLLING_INTERVAL, timeout=30)
                if playerOrHora == 'hora':
                    continue
                else:
                    player = playerOrHora

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
                    self.state['player_info'][self.last_player]['kawa_index'] += 1
                    self.phase = Phase.Tsumo

            elif self.phase == Phase.Hora:
                break
        
        self.print_mjai()
        return
    
    def notify(self, message):
        self.mjai.append(message)
        return

    def print_mjai(self):
        print('^^^^^^^^^^- mjai -^^^^^^^^^^')
        for e in self.mjai:
            str = json.dumps(e)
            print(str)

    # None = 'none',
    # StartGame = 'start_game',
    # StartKyoku = 'start_kyoku',
    # Tsumo = 'tsumo',
    # Dahai = 'dahai',
    # Chi = 'chi',
    # Pon = 'pon',
    # Daiminkan = 'daiminkan',
    # Kakan = 'kakan',
    # Ankan = 'ankan',
    # Dora = 'dora',
    # Reach = 'reach',
    # ReachAccepted = 'reach_accepted',
    # Hora = 'hora',
    # Ryukyoku = 'ryukyoku',
    # EndKyoku = 'end_kyoku',
    # EndGame = 'end_game'

if __name__ == "__main__":
    try:
        game = Game()
        asyncio.run(game.main())
    # except RuntimeError as e:
    except Exception as e:
        save_img_q()
        raise e
    except KeyboardInterrupt:
        print_with_color('游戏中止，打印中止时的GAME STATE', 'red')
        print(game.state)


# a = Game()
# print(a.state)

# a.claim(1, { 'tile': '4p', 'type': 'ankan'})

# print(a.state)