import asyncio
import time

import cv2
import numpy as np
from gamestate import get_gamestate
from util import concat_images_horizontal, create_polling_sync, stable_func
from screenshot import get_screenshot, set_debug_screenshot
from config import *
from tile import check_tile, TileType

def rec_hand():
    img = get_screenshot(save=1)
    x,y,w,h = HAND_FIRST_REGION
    tiles = []
    imgs = []
    for i in range(13):
        offset = i * w
        tile_img = img[y - 95:y + h + 95,x + offset:x + offset + w]
        tile = check_tile(tile_img, type=TileType.Hand, autocrop = False, debug=False)
        if tile is None:
            return None
        tiles.append(tile)
        imgs.append(tile_img)
    # concat_images_horizontal(imgs, 10, debug = True)
    return tiles

def rec_tsumo():
    x,y,w,h = HAND_FIRST_REGION
    gamestate = get_gamestate()
    id = gamestate['player_to_id']['self']

    meld_len = len(gamestate['player_info'][id]["melds"])
    x = x + w * 13 - meld_len * 3 * w + DRAWN_GAP
    drawn = get_screenshot((x, y - 90, w, h + 90), save=5) # 这里增加识别区的高度，是因为有可能鼠标hover时，牌上浮导致识别不到。
    # cv2.imshow('drawn', drawn)
    # cv2.waitKey(0)
    # cv2.destroyWindow('drawn')
    tile = check_tile(drawn, 'self', type=TileType.Hand)
    return tile


check_tsumo = stable_func(rec_tsumo)

# set_debug_screenshot('./logs/20260620_143100/0008_rec_hand_L13.jpg')
# res = rec_hand()
# print(res)
