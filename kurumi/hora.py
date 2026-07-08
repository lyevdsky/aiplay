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
    # TODO 流局判断不准确，一个长和牌动画后，再展示ron动作。
    screenshot = get_screenshot(CONFIRM_REGION, save=5)
    ratio = compute_mask_ratio(screenshot, CONFIRM_BG_HSV)
    ratio2 = compute_mask_ratio(screenshot, CONFIRM_TEXT_HSV)
    return (ratio + ratio2) > 0.85

def is_interrupt(shot):
    x,y,w,h = DORA_FIRST_REGION
    doraimg = shot[y:y+h, x:x+w]
    cs = find_contour(doraimg, WHILE_HSV, min_area= w * h * 0.9, debug=False)

    if len(cs) == 0:
        cs = find_contour(doraimg, SAME_TILE_HIGHLIGHT_HSV, min_area= w * h * 0.9, debug=False)
    return len(cs) == 0

# 终局中断的「检测 + 分辨 hora/ryukyoku」已整体移入 ChangeWatcher._loop：
# is_interrupt 命中后由 watcher 阻塞轮询 is_hora / is_ryukyoku 并推入 end_q。

# set_debug_screenshot('./error/0403_is_ryukyoku_L19.jpg')

# res = is_interrupt()
# print(res)
# res = check_interrupt()
# print(res)
# bool = is_hora()
# print(bool)