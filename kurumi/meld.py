PREV_MELD_FIRST_REGION = (130,1030,200,280)
import time
import cv2
import numpy as np
from gamestate import get_gamestate
from screenshot import get_screenshot, set_debug_screenshot
from tile import check_tiles
from util import stable_func
from config import TILE_WHILE_HSV, WHILE_HSV

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
def rec_kakan():
    shot = get_screenshot(save=5)
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
def rec_new_meld():
    player, melds = get_current_player_info()
    # melds = [{ 'type': 'chi'}, { 'type': 'pon' }, { 'type': 'chi' }]
    # melds = [{ 'type': 'pon'}, { 'type': 'ankan' }, {'type': 'pon'}]
    # melds = [{ 'type': 'chi'}]
    # melds = []
    # player = 'prev'
    x,y,w,h = get_meld_region(player, melds, len(melds))
    img = get_screenshot((x,y,w,h), save=5)

    result = check_tiles(img, player, debug=False)
    # print(result)
    meld = None
    if len(result) == 2:
        if result[0]['tile'] == result[1]['tile']:
            x1,y1,w1,h1 = result[0]['region']
            x2,y2,w2,h2 = result[1]['region']
            # 两种牌必须相邻，避免检测到自己手牌两种相同的牌就认为是ankan
            if (abs(x1 + w1 - x2) < 10 or abs(x2 + w2 - x1) < 10):
                # 暗杠应该是识别不出红5的
                meld = {
                    'tile': result[0]['tile'],
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

# for i in range(10):
#     print(i)
#     set_debug_screenshot(f'./logs/20260615_133324/000{i}.jpg')
#     rec_new_meld()

# set_debug_screenshot('./logs/20260617_154527/0009.jpg')
# res = rec_new_meld()
# print(res)

stabled_rec_new_meld = stable_func(rec_new_meld)

def check_new_meld():
    count = 0
    while count < 20:
        meld = stabled_rec_new_meld()
        if meld is not None:
            return meld
        time.sleep(0.5)
        count += 1
    else:
        raise RuntimeError('未识别出新的副露')

stabled_rec_kakan = stable_func(rec_kakan)
def check_kan():
    kakan_meld = stabled_rec_kakan()
    if kakan_meld is not None:
        return kakan_meld
    ankan_meld = stabled_rec_new_meld()
    if ankan_meld is not None:
        return ankan_meld
    return None

