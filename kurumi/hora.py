import cv2
import time
from util import has_template, stable_func
from screenshot import get_screenshot, set_debug_screenshot
from config import HORA_HSV, RYUKYOKU_HSV, HORA_REGION, RYUKYOKU_REGION, POLLING_INTERVAL
from kyoku import get_oya

ron_template = cv2.imread('./ref/kyoku/hora.png')
tsumo_template = cv2.imread('./ref/kyoku/tsumo.png')
ryukyoku_template = cv2.imread('./ref/kyoku/ryukyoku.png')

def is_hora():
    screenshot = get_screenshot(HORA_REGION)
    bool = has_template(screenshot, ron_template, hsv = HORA_HSV, debug=False)
    if not bool:
        bool = has_template(screenshot, tsumo_template, hsv = HORA_HSV, debug=False)
    print('check hora: ', bool)
    return bool

check_hora = stable_func(is_hora)

def is_ryukyoku():
    screenshot = get_screenshot(RYUKYOKU_REGION)
    bool = has_template(screenshot, ryukyoku_template, hsv = RYUKYOKU_HSV, debug=False)
    print('check ryukyoku: ', bool)
    return bool

check_ryukyoku = stable_func(is_ryukyoku)

def check_interrupt():
    screenshot = get_screenshot()
    oya = get_oya(screenshot)
    if oya is not None:
        return None

    print('check_interrupt: True')
    hora = check_hora()
    if hora:
        return 'hora'
    ryukyoku = check_ryukyoku()
    if ryukyoku:
        return 'ryukyoku'

        
    
# for i in range(10):
#     set_debug_screenshot(f'./logs/20260614_123432/000{i}.jpg')
#     is_hora()
# set_debug_screenshot('./video/ryukyoku.png')
# check_interrupt()
# bool = is_hora()
# print(bool)