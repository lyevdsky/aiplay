import cv2
import time
from tile import check_tile
from util import has_template, stable_func, find_contour
from screenshot import get_screenshot, set_debug_screenshot, save_img_q
from config import HORA_HSV, RYUKYOKU_HSV, HORA_REGION, RYUKYOKU_REGION, POLLING_INTERVAL, DORA_FIRST_REGION, WHILE_HSV

ron_template = cv2.imread('./ref/kyoku/hora.png')
tsumo_template = cv2.imread('./ref/kyoku/tsumo.png')
ryukyoku_template = cv2.imread('./ref/kyoku/ryukyoku.png')
dora5_template = None
_prev_is_hora = False
def is_hora():
    global _prev_is_hora
    screenshot = get_screenshot(HORA_REGION, save=5)
    bool = has_template(screenshot, ron_template, hsv = HORA_HSV, debug=False)
    if not bool:
        bool = has_template(screenshot, tsumo_template, hsv = HORA_HSV, debug=False)
    if _prev_is_hora and not bool:
        save_img_q('./logs/is_hora_error')
    _prev_is_hora = bool
    print('check hora: ', bool)
    return bool

def is_ryukyoku():
    screenshot = get_screenshot(RYUKYOKU_REGION, save=5)
    bool = has_template(screenshot, ryukyoku_template, hsv = RYUKYOKU_HSV, debug=False)
    print('check ryukyoku: ', bool)
    return bool

def is_interrupt():
    global dora5_template
    x,y,w,h = DORA_FIRST_REGION
    if dora5_template is None:
        dora5_template = get_screenshot((x + w * 4 + 5, y + 5,w - 10,h - 10), save=1)
    shot = get_screenshot(save=10)
    doraimg = shot[y:y+h,x:x+w]
    cs = find_contour(doraimg, WHILE_HSV, min_area= w * h * 0.9, debug=False)
    # 避免同牌提示导致的误判，可能需要关闭同牌提示
    if len(cs) != 0:
        return False

    bool = has_template(shot[y:y+h, x+w*4:x+w*5], dora5_template, debug=False)
    return not bool

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
        time.sleep(5)

# set_debug_screenshot('./imgs/error/dora1_error.png')

# res = is_interrupt()
# print(res)
# bool = is_hora()
# print(bool)