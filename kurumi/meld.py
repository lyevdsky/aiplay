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

REC_PREV_W_H = (200, 280) # w h
REC_SELF_W_H = (400, 150)
REC_ACROSS_W_H = (300, 100)

def crop_and_preprocess(shot, player, region):
    """裁出 region 的副本并做预处理，返回裁剪后的图。
    只拷贝 region 大小的内存，原 shot 不被修改（recorder 快照保持原始像素）。
    阴影区增亮只作用于它与 region 的交集。"""
    with timed('preprocess_screenshot'):
        x, y, w, h = region
        H, W = shot.shape[:2]
        # 夹到图像范围内，避免负坐标触发 numpy 的回绕切片
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, W), min(y + h, H)
        img = shot[y0:y1, x0:x1].copy()

        # 一番街名字的阴影导致亮度变低影响牌面的轮廓识别，这里进行亮度增强
        NEXT_SHADOW_ROI = (2060, 195, 30, 32)
        if player == 'next' and img.size > 0:
            rx, ry, rw, rh = NEXT_SHADOW_ROI
            ix0, iy0 = max(rx, x0), max(ry, y0)
            ix1, iy1 = min(rx + rw, x1), min(ry + rh, y1)
            if ix0 < ix1 and iy0 < iy1:
                sub = img[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0]   # 视图，改它即改 img
                hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
                hsv[:, :, 2] = cv2.add(hsv[:, :, 2], 40)          # V +40，饱和到 255
                sub[:] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return img

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
            region = (x, y, REC_ACROSS_W_H[0], REC_ACROSS_W_H[1])
        else:
            region = (x, y, x2 - x, REC_ACROSS_W_H[1])

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


# 识别是否存在加杠
def rec_kakan(shot, player, melds):
    for i, meld in enumerate(melds):
        if meld['type'] == 'pon':
            x, y, w, h = get_meld_region(player, melds, i)
            result = check_tiles(shot[y:y+h,x:x+w], player, debug=False)
            if len(result) == 4:
                # 这里要复制，不能直接改原meld。
                kakan_meld = {
                    'type': 'kakan',
                    'tile': meld['tile'],
                    'consumed': meld['consumed']
                }
                return kakan_meld
    return None

# 加杠另外单独识别
# 识别当前玩家是否有新副露
def rec_new_meld(shot, player, melds):
  with timed('rec_new_meld'):
    x, y, w, h = get_meld_region(player, melds, len(melds))
    img = crop_and_preprocess(shot, player, (x, y, w, h))
    if img.size == 0:
        return None
    result = check_tiles(img, player, debug=False)
    # melds = [{ 'type': 'pon'}, { 'type': 'ankan' }, {'type': 'pon'}]
    # melds = [{ 'type': 'chi'}]
    # melds = []
    # player = 'next'

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


# set_gamestate({'honba': 1, 'kyotaku': 0, 'bakaze': 'S', 'kyoku': 4, 'last_player': 2, 'last_dahai': '7z', 'dora_markers': ['9m'], 'scores': [55800, 18900, 7100, 18200], 'players': [0, 1, 2, 3], 'position': ['across', 'prev', 'self', 'next'], 'current_player': 0, 'player_to_id': {'self': 2, 'next': 3, 'across': 0, 'prev': 1}, 'oya': 3, 'player_info': [{'kawa_index': 7, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 7, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 6, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 7, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 2})
# for i in range(5):
#     print(i)
#     set_debug_screenshot(f'./logs/20260630_232119/snapshot_05_rec_new_meld_L132/000{i}_rec_new_meld_L132.jpg')
#     res = rec_new_meld()
#     print(res)
# _state_3 = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'last_player': 0, 'last_dahai': '4z', 'dora_markers': ['3m', '4s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 0, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 14, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['2z', '2z'], 'tile': '2z'}, {'type': 'pon', 'consumed': ['1m', '1m'], 'tile': '1m'}, {'type': 'daiminkan'}], 'riichi': False}, {'kawa_index': 12, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 11, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
# set_gamestate(_state_3)

# shot = cv2.imread('./error/0412__loop_L152.png')
# shot = cv2.imread('./logs/dump/20261024_152039_exception/frames/0014503.png')
# res = rec_kakan(shot)
# print(res)
# cv2.imshow('shot', shot)
# cv2.waitKey()
# res = rec_new_meld(shot)
# print(res)
