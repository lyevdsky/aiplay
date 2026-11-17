import asyncio
import time

import cv2
import numpy as np
from gamestate import get_gamestate
from util import concat_images_horizontal, create_polling_sync, stable_func
from screenshot import get_screenshot, set_debug_screenshot
from config import *
from tile import check_tile, TileType

def rec_hand(shot=None, gs=None):
    """读自己手牌（不含摸牌）。张数随副露减少：13 - 3 * 副露数。

    shot/gs 不传则用当前截图和全局 gamestate（兼容原有调用点）。
    """
    if shot is None:
        shot = get_screenshot(save=1)
    if gs is None:
        gs = get_gamestate()
    my_id = gs['player_to_id']['self']
    meld_len = len(gs['player_info'][my_id]['melds'])
    x,y,w,h = HAND_FIRST_REGION
    tiles = []
    imgs = []
    for i in range(max(13 - 3 * meld_len, 0)):
        offset = i * w
        tile_img = shot[y - 95:y + h,x + offset:x + offset + w]
        tile = check_tile(tile_img, type=TileType.Hand, debug=False)
        if tile is None:
            return None
        tiles.append(tile)
        imgs.append(tile_img)
    # concat_images_horizontal(imgs, 10, debug = True)
    return tiles

def rec_tsumo(shot=None, gs=None):
    """读自己摸到的那张牌；没摸牌返回 None。

    shot/gs 不传则用当前截图和全局 gamestate（兼容原有调用点）。
    """
    if shot is None:
        shot = get_screenshot()
    if gs is None:
        gs = get_gamestate()
    x,y,w,h = HAND_FIRST_REGION
    id = gs['player_to_id']['self']

    meld_len = len(gs['player_info'][id]["melds"])
    x = x + w * 13 - meld_len * 3 * w + DRAWN_GAP
    drawn = shot[y - 90:y + h, x:x + w] # 这里增加识别区的高度，是因为有可能鼠标hover时，牌上浮导致识别不到。
    # cv2.imshow('drawn', drawn)
    # cv2.waitKey(0)
    # cv2.destroyWindow('drawn')
    tile = check_tile(drawn, 'self', type=TileType.Hand)
    return tile


check_tsumo = stable_func(rec_tsumo)

# set_debug_screenshot('./imgs/t1//0432__loop_L152.png')
# shot = get_screenshot()
# res = rec_tsumo(shot)
# print(res)
