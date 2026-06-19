import time
import cv2
from util import has_template, ocr_digits, find_contour, stable_func, polling
from screenshot import get_screenshot, save_img_q, set_debug_screenshot
from gamestate import get_gamestate
from config import *
from tile import check_tile
from hand import rec_hand

def get_honba(screenshot):
    x,y,w,h = HONBA_REGION
    honba_img = screenshot[y:y+h, x:x+w]
    res = ocr_digits(honba_img)
    return res

def get_kyotaku(screenshot):
    x,y,w,h = KYOTAKU_REGION
    kyotaku_img = screenshot[y:y+h, x:x+w]
    res = ocr_digits(kyotaku_img)
    return res

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
    elif has_template(bakaze_img, bakazeS, hsv = BAKAZE_HSV):
        bakaze = 'S'
    else:
        bakaze = 'W'
    if has_template(kyokunum_img, kyoku4, hsv = BAKAZE_HSV):
        kyokunum = 4
    elif has_template(kyokunum_img, kyoku3, hsv = BAKAZE_HSV):
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
    return bakaze, kyokunum

def get_oya(screenshot):
    x,y,w,h = CENTER_REGION
    center = screenshot[y:y+h, x:x+w]
    cs = find_contour(center, OYA_HSV, debug=False)

    if len(cs) == 0:
        return None
        
    x, y, w, h = cv2.boundingRect(cs[0])
    if x < 200:
        oya = 'prev' if y < 100 else 'self'
    else:
        oya = 'across' if y < 100 else 'next'
    
    return oya

def get_dora_marker(screenshot, index = 0):
    x,y,w,h = DORA_FIRST_REGION
    x = x + index * w
    doraimg = screenshot[y:y+h,x:x+w]
    tile = check_tile(doraimg)
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
    print('kyoku info: ', kyoku_info)
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
        hsv = cv2.cvtColor(region_img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, ACTIVE_HSV[0], ACTIVE_HSV[1])
        # cv2.imshow('mask', mask)
        # cv2.waitKey(0)
        active = cv2.countNonZero(mask) / (w * h) > 0.9
        if active:
            return p

stabled_get_dora_marker = stable_func(get_dora_marker)
def check_new_dora_marker():
    screenshot = get_screenshot()
    gamestate = get_gamestate()
    return stabled_get_dora_marker(screenshot, len(gamestate['dora_markers']))

# player change 和 hora要同时check，所以这里不使用while True阻塞
def _check_player_change():
    gamestate = get_gamestate()
    # print('check player change')
    p = get_active_player()
    if p is not None:
        pid = gamestate['player_to_id'][p]
        if pid != gamestate['current_player']:
            return pid
    return None

check_player_change = stable_func(_check_player_change)

def wait_new_kyoku():
    print('wait new kyoku')
    def check_new_kyoku():
        screenshot = get_screenshot()
        marker = stabled_get_dora_marker(screenshot, 0)
        if marker is not None:
            return True
            
        return None
    
    try:
        polling(check_new_kyoku, POLLING_INTERVAL, timeout = 300)
        # 等待手牌准备就绪
        polling(rec_hand, POLLING_INTERVAL, timeout = None)
        time.sleep(0.5)
        return True
    except:
        return False
    
# set_debug_screenshot('./imgs/hora_2.jpg')
# wait_new_kyoku()
# res = get_active_player()
# print(res)

# rec_kyoku_info()
# cv2.waitKey(0)
# get_dora_marker(get_screenshot(), 0)
# get_scores(screenshot)
# res = rec_kyoku_info(screenshot)
# get_honba(screenshot)
# get_kyotaku(screenshot)
# print(res)
