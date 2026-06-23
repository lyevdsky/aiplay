import cv2
import time
from tile import check_tile
from util import has_template, stable_func, find_contour
from screenshot import get_screenshot, set_debug_screenshot, save_img_q
from config import HORA_HSV, RYUKYOKU_HSV, HORA_REGION, RYUKYOKU_REGION, POLLING_INTERVAL, DORA_FIRST_REGION, WHILE_HSV, SAME_TILE_HIGHLIGHT_HSV

ron_template = cv2.imread('./ref/kyoku/hora.png')
tsumo_template = cv2.imread('./ref/kyoku/tsumo.png')
ryukyoku_template = cv2.imread('./ref/kyoku/ryukyoku.png')
dora5_template = None
_prev_is_hora = False
def is_hora(shot=None):
    global _prev_is_hora
    if shot is None:
        screenshot = get_screenshot(HORA_REGION, save=5)
    else:
        x,y,w,h = HORA_REGION
        screenshot = shot[y:y+h, x:x+w]
    bool = has_template(screenshot, ron_template, hsv = HORA_HSV, debug=False)
    if not bool:
        bool = has_template(screenshot, tsumo_template, hsv = HORA_HSV, debug=False)
    if _prev_is_hora and not bool:
        save_img_q('./logs/is_hora_error')
    if _prev_is_hora and bool: # 两次True已经结束流程了，需要重置_prev_is_hora
        _prev_is_hora = False
    else:
        _prev_is_hora = bool
    return bool

def is_ryukyoku(shot=None):
    if shot is None:
        screenshot = get_screenshot(RYUKYOKU_REGION, save=5)
    else:
        x,y,w,h = RYUKYOKU_REGION
        screenshot = shot[y:y+h, x:x+w]
    bool = has_template(screenshot, ryukyoku_template, hsv = RYUKYOKU_HSV, debug=False)
    return bool

def is_interrupt(shot=None):
    global dora5_template
    x,y,w,h = DORA_FIRST_REGION
    # if dora5_template is None:
    #     dora5_template = get_screenshot((x + w * 4 + 5, y + 5,w - 10,h - 10), save=1)
    if shot is None:
        shot = get_screenshot(save=10)
    doraimg = shot[y:y+h,x:x+w]
    cs = find_contour(doraimg, WHILE_HSV, min_area= w * h * 0.9, debug=False)

    if len(cs) == 0:
        cs = find_contour(doraimg, SAME_TILE_HIGHLIGHT_HSV, min_area= w * h * 0.9, debug=False)
    return len(cs) == 0
    # 因为增加了同牌提示的识别，所以可以不需要了 
    # # 避免同牌提示导致的误判，可能需要关闭同牌提示
    # if len(cs) != 0:
    #     return False
    # # 关闭同牌提示，这里就没必要再找第5个牌了
    # bool = has_template(shot[y:y+h, x+w*4:x+w*5], dora5_template, debug=False)
    # return not bool

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

# set_debug_screenshot('./error/0009_is_interrupt_L39.jpg')

# res = is_interrupt()
# print(res)
# bool = is_hora()
# print(bool)