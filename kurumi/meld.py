PREV_MELD_FIRST_REGION = (130,1030,200,280)
import time
import cv2
import numpy as np
from gamestate import get_gamestate, set_gamestate
from screenshot import get_screenshot, set_debug_screenshot
from tile import check_tiles
from util import stable_func, timed
from config import POLLING_INTERVAL

SELF_POINTS = [(2370, 1320), (2276, 1320)]
PREV_POINTS = [(147, 1266),(164, 1198),(180,1130), (253,843)]
PREV_NUM = [0, 1, 2, 6.6]
NEXT_POINTS = [(2115, 60), (2125, 98), (2134,138), (2182, 333)]
NEXT_NUM = [0, 1, 2, 6.6]
SELF_POINTS = [(2370, 1320), (2276, 1320)]
SELF_NUM = [0, 1]
ACROSS_POINTS = [(495, 30), (562, 30)]
ACROSS_NUM = [0, 1]

REC_PREV_W_H = (200, 250) # w h
REC_SELF_W_H = (400, 150)

def computed_next_point(player, melds):
    a = 0
    b = 0
    for meld in melds:
        if meld['type'] == 'ankan':
            a += 4
        elif meld['type'] == 'daiminkan':
            a += 3
            b += 1
        else:
            a += 2
            b += 1
    if player == 'self':
        points = SELF_POINTS
        nums = SELF_NUM
        deg = 1
    elif player == 'prev':
        points = PREV_POINTS
        nums = PREV_NUM
        deg = 2
    elif player == 'across':
        points = ACROSS_POINTS
        nums = ACROSS_NUM
        deg = 1
    elif player == 'next':
        points = NEXT_POINTS
        nums = NEXT_NUM
        deg = 2

    x_idx = np.array(nums)
    x_coords = np.array([p[0] for p in points])
    y_coords = np.array([p[1] for p in points])

    # 分别拟合二次多项式
    coeff_x = np.polyfit(x_idx, x_coords, deg)   # 系数用于计算给定索引时的 x 坐标
    coeff_y = np.polyfit(x_idx, y_coords, deg)   # 系数用于计算给定索引时的 y 坐标

    # 创建多项式函数
    poly_x = np.poly1d(coeff_x)
    poly_y = np.poly1d(coeff_y)

    return (poly_x(a + b * 1.3), poly_y(a + b * 1.3))

def get_meld_region(player, melds, index):
    x,y = computed_next_point(player, melds[:index])
    if index < len(melds):
        x2,y2 = computed_next_point(player, melds[:index + 1])

    if player == 'prev':
        if index >= len(melds):
            region = (x, y - REC_PREV_W_H[1], REC_PREV_W_H[0], REC_PREV_W_H[1])
        else:
            region = (x, y2, REC_PREV_W_H[0], y - y2)

    elif player == 'across':
        if index >= len(melds):
            region = (x, y, REC_SELF_W_H[0], REC_SELF_W_H[1])
        else:
            region = (x, y, x2 - x, REC_SELF_W_H[1])

    elif player == 'next':
        if index >= len(melds):
            region = (x - REC_PREV_W_H[0] + 50, y, REC_PREV_W_H[0], REC_PREV_W_H[1])
        else:
            region = (x2 - REC_PREV_W_H[0], y, REC_PREV_W_H[1], y2 - y)
    
    elif player == 'self':
        if index >= len(melds):
            region = (x - REC_SELF_W_H[0], y - REC_SELF_W_H[1], REC_SELF_W_H[0], REC_SELF_W_H[1])
        else:
            region = (x2, y - REC_SELF_W_H[1], x - x2, REC_SELF_W_H[1])

    return list((int(x) for x in region))


def get_current_player_info():
    gamestate = get_gamestate()
    position = gamestate['position']
    player_pos = position[gamestate['current_player']]
    player_info = gamestate['player_info'][gamestate['current_player']]
    melds = player_info['melds']
    return player_pos, melds

# 识别是否存在加杠
def rec_kakan(shot):
    player, melds = get_current_player_info()
    for i, meld in enumerate(melds):
        if meld['type'] == 'pon':
            x,y,w,h = get_meld_region(player, melds, i)
            result = check_tiles(shot[y:y+h,x:x+w], player, debug=False)
            if len(result) == 4:
                # 这里识别到加杠需要改type，
                meld['type'] = 'kakan'
                return meld
    return None

# 加杠另外单独识别
# 识别当前玩家是否有新副露
def rec_new_meld(shot):
  with timed('rec_new_meld'):
    player, melds = get_current_player_info()
    # melds = [{ 'type': 'chi'}, { 'type': 'pon' }, { 'type': 'chi' }]
    # melds = [{ 'type': 'pon'}, { 'type': 'ankan' }, {'type': 'pon'}]
    # melds = [{ 'type': 'chi'}]
    # melds = []
    # player = 'next'
    x,y,w,h = get_meld_region(player, melds, len(melds))
    img = shot[y:y+h, x:x+w]
    # cv2.imshow('img', img)
    # cv2.waitKey()
    result = check_tiles(img, player, debug=False)
    # print(result)
    meld = None
    if len(result) == 2:
        num, suit = result[0]['tile']
        num1, suit1 = result[1]['tile']
        if suit != suit1:
            return None
        if num == num1 or (num == '0' and num1 == '5') or (num == '5' and num1 == '0'):
            x1,y1,w1,h1 = result[0]['region']
            x2,y2,w2,h2 = result[1]['region']
            # 如果是自己，两种牌必须相邻，避免检测到自己手牌和摸牌两种相同的牌就认为是ankan
            if (player == 'self' and abs(x1 + w1 - x2) > 10 and abs(x2 + w2 - x1) > 10):
                return None
        
            meld = {
                'tile': (num if num != 0 else 5) + suit,
                'type': 'ankan'
            }
    elif len(result) == 4:
        meld = {
            'type': 'daiminkan'
        }
    elif len(result) == 3:
        consumed = []
        tile = None
        for r in result:
            if r['direction'] == player:
                consumed.append(r['tile'])
            else:
                tile = r['tile']
        # 识别异常直接返回None
        if len(consumed) != 2:
            return None
        if consumed[0] == consumed[1] or consumed[0] == tile or consumed[1] == tile:
            meld = {
                'type': 'pon',
                'consumed': consumed,
                'tile': tile
            }
        else:
            meld = {
                'type': 'chi',
                'consumed': consumed,
                'tile': tile
            }
    
    # print(f'check {player} meld result: ', meld)
    return meld
# set_gamestate({'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 4, 'dora_markers': ['6m'], 'scores': [34000, 18600, 17000, 30400], 'players': [0, 1, 2, 3], 'position': ['prev', 'self', 'next', 'across'], 'current_player': 1, 'player_to_id': {'self': 1, 'next': 2, 'across': 3, 'prev': 0}, 'oya': 3, 'player_info': [{'kawa_index': 3, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 3, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 2, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 3, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 1})

# for i in range(5):
#     print(i)
#     set_debug_screenshot(f'./logs/20260629_231436/snapshot_05_rec_new_meld_L132/000{i}_rec_new_meld_L132.jpg')
#     res = rec_new_meld()
#     print(res)

# set_debug_screenshot('./error/0004_rec_new_meld_L132.jpg')
# # # # # # # # set_debug_screenshot('./logs/20260617_154527/0009.jpg')
# res = rec_new_meld()
# print(res)

stabled_rec_new_meld = stable_func(rec_new_meld)
stabled_rec_kakan = stable_func(rec_kakan)

# 新副露：吃/碰/暗杠/大明杠，扫「下一副露位」识别。
def check_new_meld(shot):
    return stabled_rec_new_meld(shot)

# 加杠：既有的碰升级成杠，原地不占新副露位，rec_new_meld 扫不到，需单独识别。
def check_kakan(shot):
    return stabled_rec_kakan(shot)
