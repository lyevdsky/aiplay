import asyncio

import cv2
import numpy as np
import math
from gamestate import get_gamestate
from screenshot import get_screenshot, save_img_q, set_debug_screenshot
from util import concat_images_horizontal, find_contour, stable_func, timed
from config import *
from tile import check_tile
from hand import rec_tsumo

def crop_kawa_tile(player, pos, riichi_index = None):
    row = pos // 6
    col = pos % 6
    is_riichi_tile = pos == riichi_index
    has_riichi_offset = False if riichi_index == None else (riichi_index // 6) == (pos // 6) and not is_riichi_tile
    if player == 'self':
        x1, y1, w, h = MINE_KAWA_FIRST_REGION
        x = x1 + col * w
        y = y1 + row * h

    if player == 'next':
        x1, y1, w, h = NEXE_KAWA_FIRST_REGION
        x = x1 + row * w - round(col * 4.5)
        y = y1 - col * h + round(col * 0.2)
        h = h - col
        w = w - col
        # return cv2.rotate(screenshot[y:y+h, x:x+w], cv2.ROTATE_90_CLOCKWISE)

    if player == 'across':
        x1, y1, w, h = ACROSS_KAWA_FIRST_REGION
        x = x1 - col * w - row * 2 
        y = y1 - row * h
        h = h - row
        # return cv2.rotate(screenshot[y:y+h, x:x+w], cv2.ROTATE_180)

    if player == 'prev':
        x1, y1, w, h = PREV_KAWA_FIRST_REGION
        x = x1 - row * w - round(col * 5)
        y = y1 + col * h + round(col * 6)
        h = h + round(col * 1.5)
        w = w + col
        # return cv2.rotate(screenshot[y:y+h, x:x+w], cv2.ROTATE_90_COUNTERCLOCKWISE)
    return x,y,w,h

def rec_dahai(player, pos, riichi_index, debug=False):
  with timed('rec_dahai'):
    x,y,w,h = crop_kawa_tile(player, pos, riichi_index)

    if player == 'self':
        w = w + 30
    elif player == 'next':
        h = h + 30
        y = y - 30
    elif player == 'across':
        x = x - 30
        w = w + 30
    else:
        h = h + 30

    img = get_screenshot((x,y,w,h), save=100)
    result = check_tile(img, player, return_dict=True, debug=debug)
    # print(result)
    if result is None:
        return None
    
    x,y,w,h = result['region']
    tileimg = img[y:y+h,x:x+w]

    # 判断tsumogiri
    cs = find_contour(tileimg, WHILE_HSV, 300)
    tsumogiri = len(cs) == 0

    riichi = False

    if player == 'self' and w / h > 1.5:
        riichi = True
    elif player == 'next' and w / h < 1.8:
        riichi = True
    elif player == 'across' and w / h > 1.5:
        riichi = True
    elif player == 'prev' and w / h < 1.5:
        riichi = True

    return result['tile'], tsumogiri, riichi

def crop_kawa_all_tiles(player):
    # screenshot = cv2.imread('./imgs/riichi/0.png')
    screenshot = cv2.imread('./screenshots/390.png')
    pos = 0
    tiles = []
    while pos < 15:
        tile_region = crop_kawa_tile(player, pos)
        x,y,w,h = tile_region
        tile = screenshot[y:y+h,x:x+w]
        tiles.append(tile)
        pos += 1

    concat_images_horizontal(tiles, 12, (255, 0, 0), debug=False)
    return tiles

# dahai 和 kakan ankan hora要同时check，所以这里不使用while True阻塞
def _check_dahai():
    gamestate = get_gamestate()
    position = gamestate['position']
    player_pos = position[gamestate['current_player']]
    player_info = gamestate['player_info'][gamestate['current_player']]

    result = rec_dahai(player_pos, player_info['kawa_index'], player_info['riichi_index'])
    if result is not None:
        tile, tsumogiri, riichi = result
        return tile, tsumogiri, riichi

check_dahai = stable_func(_check_dahai, debug=False)

def check_dahai_claimed():
    # gamestate = {'honba': 0, 'kyotaku': 0, 'bakaze': 'E', 'kyoku': 1, 'dora_markers': ['5s'], 'scores': [25000, 25000, 25000, 25000], 'players': [0, 1, 2, 3], 'position': ['self', 'next', 'across', 'prev'], 'current_player': 1, 'player_to_id': {'self': 0, 'next': 1, 'across': 2, 'prev': 3}, 'oya': 0, 'player_info': [{'kawa_index': 2, 'riichi_index': None, 'melds': [], 'riichi': False}, {'kawa_index': 2, 'riichi_index': None, 'riichi': False, 'melds': []}, {'kawa_index': 2, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 2, 'riichi': False, 'riichi_index': None, 'melds': []}], 'my_id': 0}
    gamestate = get_gamestate()
    position = gamestate['position']
    player_pos = position[gamestate['current_player']]
    player_info = gamestate['player_info'][gamestate['current_player']]

    result = rec_dahai(player_pos, player_info['kawa_index'], player_info['riichi_index'], debug=False)
    return result is None

# set_debug_screenshot('./error/0060_rec_dahai_L61.jpg')
# res = rec_dahai('next', 0, None, debug=True)
# print(res)
# for i in range(100):
#     # set_debug_screenshot(f'./logs/20260617_165923/000{i}.jpg')
#     res = rec_dahai('next', 0, None)
#     print(res)
#     if res is not None and res[0] == '4z':
#         save_img_q()
# print(rec_tsumo())
# if rec_tsumo() is not None:
#     res = None
# print(res)
# for i in range(180):
#     res = rec_dahai('next', 6, None)
#     if res != None and res[0] == '4z':
#         save_img_q()
#     print(res)