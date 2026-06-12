import asyncio
import time
import cv2
import numpy as np
from util import create_polling_sync, has_template, ocr_digits, to_black_on_white, find_contour, crop_min_rect, stable_func
from screenshot import get_screenshot, set_screenshot
from gamestate import get_gamestate
from config import *
from tile import predict_tile

def get_honba(screenshot):
    x,y,w,h = HONBA_REGION
    honba_img = screenshot[y:y+h, x:x+w]
    # cv2.imshow('honba_img', honba_img)
    # cv2.waitKey(0)
    _img = to_black_on_white(honba_img)
    return ocr_digits(_img)

def get_kyotaku(screenshot):
    x,y,w,h = KYOTAKU_REGION
    kyotaku_img = screenshot[y:y+h, x:x+w]
    _img = to_black_on_white(kyotaku_img)
    return ocr_digits(_img)

def get_kyoku(screenshot):
    bakazeE = cv2.imread('./ref/kyoku/bakaze_e.png')
    bakazeS = cv2.imread('./ref/kyoku/bakaze_s.png')
    kyoku1 = cv2.imread('./ref/kyoku/kyoku_1.png')
    kyoku2 = cv2.imread('./ref/kyoku/kyoku_2.png')
    kyoku3 = cv2.imread('./ref/kyoku/kyoku_3.png')
    kyoku4 = cv2.imread('./ref/kyoku/kyoku_4.png')
    x,y,w,h = BAKAZE_REGION
    bakaze_img = screenshot[y:y+h, x:x+w]
    x,y,w,h = KYOKUNUM_REGION
    kyokunum_img = screenshot[y:y+h, x:x+w]

    if has_template(bakaze_img, bakazeE, hsv = BAKAZE_HSV):
        bakaze = 'E'
    elif has_template(bakaze_img, bakazeS):
        bakaze = 'S'
    else:
        bakaze = 'W'
    if has_template(kyokunum_img, kyoku4, hsv = BAKAZE_HSV):
        kyokunum = 4
    elif has_template(kyokunum_img, kyoku3):
        kyokunum = 3
    elif has_template(kyokunum_img, kyoku2, hsv = BAKAZE_HSV):
        kyokunum = 2
    elif has_template(kyokunum_img, kyoku1, hsv = BAKAZE_HSV):
        kyokunum = 1
    else:
        kyokunum = 0
    # cv2.imshow('bakaze_img', bakaze_img)
    # cropped_bakaze = crop_min_rect(bakaze_img, BAKAZE_HSV)
    # cv2.imshow('cropped_bakaze', cropped_bakaze)
    # cv2.imwrite('./ref/bakaze_2.png', cropped_bakaze)
    # cv2.imshow('kyokunum_img', kyokunum_img)
    # cropped_kyokunum = crop_min_rect(kyokunum_img, BAKAZE_HSV)
    # cv2.imshow('cropped_kyokunum', cropped_kyokunum)
    # cv2.imwrite('./ref/kyokunum1.png', cropped_kyokunum)
    # cv2.waitKey(0)
    print(bakaze, kyokunum)
    return bakaze, kyokunum

def get_oya(screenshot):
    x,y,w,h = CENTER_REGION
    center = screenshot[y:y+h, x:x+w]
    cs = find_contour(center, [RED_HSV_1, RED_HSV_2])
   
    x, y, w, h = cv2.boundingRect(cs[0])
    if x < 200:
        oya = 'prev' if y < 100 else 'self'
    else:
        oya = 'across' if y < 100 else 'next'
    
    print('oya: ', oya)
    return oya

def get_dora_marker(screenshot, index = 0):
    x,y,w,h = DORA_FIRST_REGION
    x = x + index * w
    doraimg = screenshot[y:y+h,x:x+w]
    tile = predict_tile(doraimg)
    return tile

def get_scores(screenshot):
    x,y,w,h = SCORE_SELF_REGION
    self_score = screenshot[y:y+h,x:x+w]
    res1 = ocr_digits(self_score)
    x,y,w,h = SCORE_NEXT_REGION
    next_score = cv2.rotate(screenshot[y:y+h,x:x+w], cv2.ROTATE_90_CLOCKWISE)
    res2 = ocr_digits(next_score)
    x,y,w,h = SCORE_ACROSS_REGION
    across_score = cv2.rotate(screenshot[y:y+h,x:x+w], cv2.ROTATE_180)
    res3 = ocr_digits(across_score)
    x,y,w,h = SCORE_PREV_REGION
    prev_score = cv2.rotate(screenshot[y:y+h,x:x+w], cv2.ROTATE_90_COUNTERCLOCKWISE)
    res4 = ocr_digits(prev_score)
    # cv2.imshow('self_score', self_score)
    # cv2.imshow('next_score', next_score)
    # cv2.imshow('across_score', across_score)
    # cv2.imshow('prev_score', prev_score)
    # cv2.waitKey(0)
    print('scores start from self:', res1, res2,res3,res4)
    return [res1, res2, res3, res4]

def rec_kyoku_info():
    screenshot = get_screenshot()
    kyoku_info = {}
    kyoku_info['oya'] = get_oya(screenshot)
    kyoku_info['honba'] = get_honba(screenshot)
    kyoku_info['kyotaku'] = get_kyotaku(screenshot)
    kyoku_info['bakaze'], kyoku_info['kyokunum'] = get_kyoku(screenshot)
    kyoku_info['dora_marker'] = get_dora_marker(screenshot, index=0)
    kyoku_info['scores'] = get_scores(screenshot)

    return kyoku_info

def get_active_player():
    regions = {
        'self': ACTIVE_SELF_REGION,
        'next': ACTIVE_NEXT_REGION,
        'across': ACTIVE_ACROSS_REGION,
        'prev': ACTIVE_PREV_REGION
    }
    shot = get_screenshot()

    for p, region in regions.items():
        x,y,w,h = region
        region_img = shot[y:y+h,x:x+w]
        gray = cv2.cvtColor(region_img, cv2.COLOR_BGR2GRAY)
        active = np.sum(gray > ACTIVE_MIN_VALUE) > 300
        if active:
            return p


# player change 和 hora要同时check，所以这里不使用while True阻塞
def _check_player_change():
    gamestate = get_gamestate()
    print('check player change')
    p = get_active_player()
    if p is not None:
        pid = gamestate['player_to_id'][p]
        if pid != gamestate['current_player']:
            print('player change to: ', p)
            return pid
    return None
        
check_player_change = stable_func(_check_player_change)

# async def check_player_change():
#     stabled_get_active_player = stable_func(get_active_player)
#     async def check():
#         while True:
#             shot = screenshot()
#             gamestate = get_gamestate()
#             print('check player change')
#             p = stabled_get_active_player(shot)
#             if p is not None:
#                 pid = gamestate['player_to_id'][p]
#                 if pid != gamestate['current_player']:
#                     print('player change to: ', p)
#                     return pid
#             await asyncio.sleep(0)
#     try:
#         result = await asyncio.wait_for(check(), timeout=None)
#         return result
#     except asyncio.TimeoutError:
#         return None

check_new_dora = stable_func(get_dora_marker)

# def check_new_dora():
#     stabled_get_dora_marker = stable_func(get_dora_marker)
#     poll = create_polling_sync(stabled_get_dora_marker, 0.2, 2, '超时未识别到新宝牌指示牌')
#     return poll()

# if __name__ == "__main__":
#     asyncio.run(check_player_change())

# set_screenshot('./imgs/')
# rec_kyoku_info(screenshot)
# get_dora(screenshot, 3)
# get_scores(screenshot)
# res = rec_kyoku_info(screenshot)
# get_honba(screenshot)
# get_kyotaku(screenshot)
# print(res)