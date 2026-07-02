import warnings
warnings.filterwarnings("ignore")
import json
import time

from screenshot import get_screenshot, save_img_q
from logger_setup import save_log
from kyoku import rec_kyoku_info, check_new_dora_marker, wait_new_kyoku
from gamestate import get_gamestate, init_gamestate, set_gamestate, Phase
from hand import rec_hand, check_tsumo, rec_tsumo
from util import polling, timed
from config import POLLING_INTERVAL, IS_DEV
from pynput import keyboard
from mortal.bot import Bot
from change_watcher import ChangeWatcher
import queue

# TODO
# ai print less !
# 听牌提示 认为打牌问题 o
# 打牌太快问题。 !
# 杠 哪个问题
# 窗口最大化

def print_with_color(text, color = 'green'):
    ts = time.strftime('%H:%M:%S')
    if color == 'green':
        print(f'\033[32m {ts} [GAME] {text} \033[0m')
    elif color == 'red':
        print(f"\033[31m {ts} [GAME] {text} \033[0m")
    elif color == 'blue':
        print(f"\033[34m {ts} [AI] {text} \033[0m")

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
        if IS_DEV:
            self.bot = None
        else:
            self.bot = Bot()
        self.listener = listener
        # watcher 永远起：dev/replay 下两个读取者各持独立游标读同一帧源，
        # 复刻生产环境的并行取帧，main 流程不区分 dev/生产。
        self.watcher = ChangeWatcher()

    @property
    def phase(self):
        # phase 归属 gamestate，唯一真相源就是 gamestate['phase']；main 负责更新。
        return self.state.get('phase')

    @phase.setter
    def phase(self, value):
        self.state['phase'] = value

    # last_player / last_dahai 同样归属 gamestate：main 更新，watcher 读它们
    # 作为 dahai check 的前置条件（current_player != last_player 才检打牌）。
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
            if num == '5' and self.last_dahai != '5z':
                consumed = [self.last_dahai] * 2 + ['0' + suit]
            elif num == '0':
                consumed = ['5' + suit] * 3
            else:
                consumed = [self.last_dahai] * 3
                
            print_with_color(f'player {player} {type} < {consumed} >')
            self.notify({
                'type': type,
                'actor': player,
                'target': self.last_player,
                'pai': self.last_dahai,
                'consumed': consumed,
            })
            player_melds.append({ 'type': 'daiminkan' })

        elif type == 'ankan':
            tile = meld['tile']
            num, suit = tile
            if num == '5' and tile != '5z':
                consumed = [tile] * 3 + ['0' + suit]
            else:
                consumed = [tile] * 4
            print_with_color(f'player {player} {type} < {consumed} >')
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
            })
            player_melds.append({ 'type': 'ankan' })
        elif type == 'kakan':
            # 注意 加杠返回的是之前碰的副露内容，
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
            self.notify({
                'type': type,
                'actor': player,
                'consumed': consumed,
                'pai': pai
            })
            meld['type'] = 'kakan'

    def open_dora(self):
        dora_marker = polling(check_new_dora_marker, POLLING_INTERVAL, timeout = 5)
        self.state['dora_markers'].append(dora_marker)
        print_with_color(f'新宝牌指示牌 < {dora_marker} >')
        self.notify({
            'type': 'dora',
            'dora_marker': dora_marker
        })
        self.need_open_dora = False

    def wait_any(self, queues, timeout=None):
        """从给定队列集合取第一个可用事件。watcher 全程并行识别（含终局中断），
        转换即入队；main 只消费、不识别。用带 timeout 的轮询而非阻塞 get，
        以保持 Ctrl+C 可响应（否则会卡在 Queue 的 C 级锁里）。"""
        elapsed = 0.0
        while timeout is None or elapsed < timeout:
            for q in queues:
                try:
                    return q.get_nowait()
                except queue.Empty:
                    pass
            time.sleep(POLLING_INTERVAL)
            elapsed += POLLING_INTERVAL
        raise TimeoutError('wait_any 超时没有结果')

    @staticmethod
    def _poll(q, cur=None):
        """取队列最新事件，队列空则原样返回 cur（保留上轮未消费的值）。
        dahai_q/tsumo_q/meld_q 在 watcher 端只留最新一项，故这里每轮覆盖即取最新。"""
        try:
            return q.get_nowait()
        except queue.Empty:
            return cur

    def main(self):
        INTERVAL_TIME = 0.5
        state = self.state

        # 监视线程每局由 start_kyoku 拉起（main 在终局调用 stop 回收），此处不再统一启动
        # 所有识别（tsumo/dahai/副露/player_change/终局中断）都在 watcher 线程并行，
        # main 只在各 phase 从对应队列取/等结果，自身不做任何识别。
        # end_q（hora/ryukyoku）在每个等待点都纳入，终局中断随时可被消费。
        is_meld_make_player_change = False
        change_player = None
        meld = None
        tsumo = None
        dahai = None
        end = None
        rec_start_time = None # 开始识别dahai，tsumo等的开始时间，用于判断是否超时异常。 不过先不写了，可以主动ctrl+c终止。
        # 后续因为 没有了wait，polling。 而是while的每轮循环都会check。所以已经可以实现中断了。
        while True:
            player = state['current_player']
            with timed('get_queue'):
                # 全部队列每轮取最新（dahai_q/tsumo_q/meld_q 在 watcher 端只留最新一项）。
                meld = self._poll(self.watcher.meld_q, meld)
                dahai = self._poll(self.watcher.dahai_q, dahai)
                tsumo = self._poll(self.watcher.tsumo_q, tsumo)
                end = self._poll(self.watcher.end_q, end)
                change_player = self._poll(self.watcher.player_q, change_player)
            
            # 因为不使用check_dahai_claim
            # 需要专门处理claim阶段，判断切换玩家时是鸣牌还是正常摸牌以及后续流程
            if self.phase == Phase.Unknown:
    
                if meld is not None:
                    # 处理鸣牌阶段的鸣牌
                    if meld['type'] == 'chi':
                        self.claim(player, meld)
                        meld = None
                        self.phase = Phase.Dahai
                        self.state['player_info'][self.last_player]['kawa_index'] -= 1
                    elif meld['type'] == 'pon':
                        self.claim(player, meld)
                        meld = None
                        self.phase = Phase.Dahai
                        self.state['player_info'][self.last_player]['kawa_index'] -= 1
                    elif meld['type'] == 'daiminkan':
                        self.claim(player, meld)
                        meld = None
                        self.phase = Phase.Tsumo
                        self.need_open_dora = True
                        self.state['player_info'][self.last_player]['kawa_index'] -= 1
                    # 处理加杠和暗杠，meld先不处理，补上摸牌阶段，后续处理交由打牌阶段
                    elif meld['type'] == 'kakan':
                        self.phase = Phase.Tsumo
                    elif meld['type'] == 'ankan':
                        self.phase = Phase.Tsumo

                elif tsumo is not None:
                    self.phase = Phase.Tsumo
                elif dahai is not None:
                    # unknown阶段识别出dahai，说明是非自家正常摸牌后打牌，先补上摸牌阶段
                    self.phase = Phase.Tsumo
                elif end is not None:
                    # 需要补上摸牌阶段
                    self.phase = Phase.Tsumo
                else:
                    time.sleep(INTERVAL_TIME)
                    continue

            if self.phase == Phase.Tsumo:
                # TODO 校验
                # if (self.last_player + 1) % 4 != player:
                #     raise RuntimeError('没有鸣牌的情况下并没有正确轮到下一位玩家')
                if player == state['my_id']:
                    if tsumo is not None:
                        tile = tsumo['tile']
                        tsumo = None
                    else:
                        time.sleep(INTERVAL_TIME)
                        continue
                else:
                    tile = '?'

                self.tsumo(player, tile)
                self.phase = Phase.Dahai

            elif self.phase == Phase.Dahai:
                # 只有dahai阶段和claim阶段才有end。
                if end is not None:
                    if end['type'] == 'hora':
                        self.phase = Phase.Hora
                        continue
                    elif end['type'] == 'ryukyoku':
                        self.phase = Phase.Ryukyoku
                        continue
                if meld is not None:
                    if meld['type'] == 'ankan':
                        self.claim(player, meld)
                        meld = None
                        if self.need_open_dora:
                            self.open_dora()
                        self.open_dora()
                        self.phase = Phase.Tsumo
                    elif meld['type'] == 'kakan':
                        self.claim(player, meld)
                        meld = None
                        if self.need_open_dora:
                            self.open_dora()
                        self.need_open_dora = True
                        self.phase = Phase.Tsumo

                if dahai is None:
                    time.sleep(INTERVAL_TIME)
                    continue

                self.dahai(player, dahai['tile'], dahai['tsumogiri'], dahai['riichi'])
                dahai = None
                self.phase = Phase.Claim

            elif self.phase == Phase.Claim:
                # active bar 的亮灭转换由 watcher 全程盯着、转换即入 player_q。

                if end is not None:
                    if end['type'] == 'hora':
                        self.phase = Phase.Hora
                        continue
                    elif end['type'] == 'ryukyoku':
                        self.phase = Phase.Ryukyoku
                        continue
                if change_player is None:
                    time.sleep(INTERVAL_TIME)
                    continue
                
                player = change_player['pid']
                print_with_color(f'切换至玩家 {player}')

                # 先更新 current_player，watcher 才会按新玩家扫描副露区（meld_q）
                state['current_player'] = player
                # 切换到自己时会开始识别tsumo，这里先将tsumo清空，避免上手番的残留
                tsumo = None
                change_player = None
                
                if self.need_open_dora:
                    self.open_dora()

                if self.riichi_to_accepted is not None:
                    print('reach_accept')
                    self.notify({ 'type': 'reach_accepted', 'actor': self.riichi_to_accepted })
                    self.riichi_to_accepted = None
                    # time sleep 是为了避免立直时放立直棒的手等立直动画，挡住已打牌，错判鸣牌。
                    time.sleep(0.8)

                # TODO check_dahai_claimed是否有必要呢，因为本来轮到这个玩家后就要一直check_new_meld。
                # 那何不直接交由后续check来判断是否有鸣牌？问题是能区分明杠和加杠吗？可以区分
                # 需要注意kawa_index 可能需要先+1，如果判断是鸣牌，则需要last_plaer的kawa_index - 1，
                # 好处是少了一次rec_dahai，判断鸣牌更准确。不容易因各种原因误判鸣牌
                # 坏处是如果因为bug导致跳过了一个玩家打牌,应该raise<没有鸣牌的情况下并没有正确轮到下一位玩家>,却没有raise。是否应该检查是否正常顺序。然后raise？
                # 即是好处，又是坏处的地方就是因为没有了check_new_meld的while循环，而是和dahai阶段一样check_dahai和check_new_meld的轮流check，
                # 将check_dahai 提前了，但是感觉除了增加了check_dahai的次数没什么作用。因为提不提前都能正确判断dahai。
                # 因为现在主要的问题是立直动画导致的rec_dahai的延迟，导致的后续识别问题。

                # 不再用 check_dahai_claimed 判断是否被鸣：鸣牌必被 watcher 的 check_new_meld
                # 捕获并入 meld_q。先简单地 sleep 1s 给 watcher 识别时间，再看 meld_q 有无副露。
                # TODO: 后续把「取队列判断」上移到与 self.phase== 同级，由队列直接驱动 phase 设置；
                #       届时 kawa_index 改为「先增后减」（先假设未鸣 +1，若判定被鸣再 -1）。
                # time.sleep(1)
                self.state['player_info'][self.last_player]['kawa_index'] += 1
                self.phase = Phase.Unknown

            elif self.phase == Phase.StartKyoku:
                self.start_kyoku()
                self.phase = Phase.Tsumo

            elif self.phase == Phase.Hora:
                # TODO 最后一张ron牌难以被识别
                print_with_color('和了')
                self.watcher.stop()
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.Ryukyoku:
                print_with_color('流局')
                self.watcher.stop()
                self.phase = Phase.EndKyoku

            elif self.phase == Phase.EndKyoku:
                end = None
                tsumo = None
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

def on_press(key):
    if key == keyboard.Key.f1:
        print_with_color('按下了F1，保存最近截图', 'red')
        # 这里可以放置你的 F1 功能逻辑
        save_img_q()
    elif key == keyboard.Key.f2:
        print_with_color('按下了F2，保存日志', 'red')
        save_log('按下F2手动保存')

listener = keyboard.Listener(on_press=on_press)
listener.start()
_state_1 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 2, 'dora_markers': ['4s'], 'scores': [23000, 24500, 24500, 28000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 1, 'player_info': [{'kawa_index': 7, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 8, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 8, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 8, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
_state_2 = {'honba': 2, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 2, 'dora_markers': ['1p'], 'scores': [43000, 33900, 19300, 3800], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 2, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 1, 'player_info': [{'kawa_index': 9, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 10, 'riichi_index': None, 'riichi': False, 'melds': [{'type': 'pon', 'consumed': ['1z', '1z'], 'tile': '1z'}]}, {'kawa_index': 10, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 9, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
if __name__ == "__main__":
    game = None
    try:
        game = Game()
        # game.start_with_state(_state_2)
        # game.phase = Phase.Tsumo
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
