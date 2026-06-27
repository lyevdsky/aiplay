import cv2
import time
from util import has_template, stable_func, find_contour, compute_mask_ratio
from screenshot import get_screenshot, set_debug_screenshot, save_img_q
from config import CONFIRM_TEXT_HSV, HORA_HSV, HORA_REGION, CONFIRM_REGION, CONFIRM_BG_HSV, POLLING_INTERVAL, DORA_FIRST_REGION, WHILE_HSV, SAME_TILE_HIGHLIGHT_HSV

ron_template = cv2.imread('./ref/kyoku/hora.png')
tsumo_template = cv2.imread('./ref/kyoku/tsumo.png')

def is_hora():
    screenshot = get_screenshot(HORA_REGION, save=5)
    bool = has_template(screenshot, ron_template, hsv = HORA_HSV, debug=False)
    if not bool:
        bool = has_template(screenshot, tsumo_template, hsv = HORA_HSV, debug=False)
    
    return bool

def is_ryukyoku():
    screenshot = get_screenshot(CONFIRM_REGION, save=5)
    ratio = compute_mask_ratio(screenshot, CONFIRM_BG_HSV)
    ratio2 = compute_mask_ratio(screenshot, CONFIRM_TEXT_HSV)
    return (ratio + ratio2) > 0.85

def is_interrupt():
    x,y,w,h = DORA_FIRST_REGION
    doraimg = get_screenshot(DORA_FIRST_REGION, save=10)
    cs = find_contour(doraimg, WHILE_HSV, min_area= w * h * 0.9, debug=False)

    if len(cs) == 0:
        cs = find_contour(doraimg, SAME_TILE_HIGHLIGHT_HSV, min_area= w * h * 0.9, debug=False)
    return len(cs) == 0

def check_interrupt():
    # print('check_interrupt')
    # TODO 还是得改为识别宝牌1是否有白色区域？  z5的老是误识别
    # 因为认定为interrupt后，只要没检查到原因还是会抛出去，导致一些动画误检测为打牌z5.
    # 吃碰杠的动画，还是有可能被误识别打牌的！特别是z5
    
    if not is_interrupt():
        return None
    
    print('check_interrupt: True')
    while True:
        hora = is_hora()
        if hora:
            return 'hora'
        ryukyoku = is_ryukyoku()
        if ryukyoku:
            return 'ryukyoku'
        time.sleep(0.5)

# set_debug_screenshot('./error/0403_is_ryukyoku_L19.jpg')

# res = is_interrupt()
# print(res)
# res = check_interrupt()
# print(res)
# bool = is_hora()
# print(bool)