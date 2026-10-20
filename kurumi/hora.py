import cv2
from util import has_template, find_contour, compute_mask_ratio
from config import CONFIRM_TEXT_HSV, HORA_HSV, HORA_REGION, CONFIRM_REGION, CONFIRM_BG_HSV, DORA_FIRST_REGION, WHILE_HSV, SAME_TILE_HIGHLIGHT_HSV

ron_template = cv2.imread('./ref/kyoku/hora.png')
tsumo_template = cv2.imread('./ref/kyoku/tsumo.png')


# 三个判断都只读传入的 shot，不再自己 get_screenshot：
# 保证 watcher 一轮 step 内所有识别共用同一帧，也才能被 replay 确定性重放。

def is_hora(shot):
    x, y, w, h = HORA_REGION
    img = shot[y:y + h, x:x + w]
    found = has_template(img, ron_template, hsv=HORA_HSV, debug=False)
    if not found:
        found = has_template(img, tsumo_template, hsv=HORA_HSV, debug=False)
    return found


def is_ryukyoku(shot):
    # TODO 流局判断不准确，一个长和牌动画后，再展示ron动作。
    x, y, w, h = CONFIRM_REGION
    img = shot[y:y + h, x:x + w]
    ratio = compute_mask_ratio(img, CONFIRM_BG_HSV)
    ratio2 = compute_mask_ratio(img, CONFIRM_TEXT_HSV)
    return (ratio + ratio2) > 0.85


def is_interrupt(shot):
    x, y, w, h = DORA_FIRST_REGION
    doraimg = shot[y:y + h, x:x + w]
    cs = find_contour(doraimg, WHILE_HSV, min_area=w * h * 0.9, debug=False)

    if len(cs) == 0:
        cs = find_contour(doraimg, SAME_TILE_HIGHLIGHT_HSV, min_area=w * h * 0.9, debug=False)
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