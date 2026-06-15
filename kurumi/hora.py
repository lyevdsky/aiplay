import cv2
import time
from util import has_template, stable_func
from screenshot import get_screenshot, set_screenshot
from config import HORA_HSV
from kyoku import get_oya

hora_region = (1375, 190, 220, 145)
hora_template = cv2.imread('./ref/kyoku/hora.png')

def is_hora():
    screenshot = get_screenshot(hora_region)
    bool = has_template(screenshot, hora_template, hsv = HORA_HSV, debug=False)
    print('check hora: ', bool)
    return bool

check_hora = stable_func(is_hora)

def check_interrupt():
    i = 0
    # print('check_interrupt')
    while i < 3:
        screenshot = get_screenshot()
        oya = get_oya(screenshot)
        if oya is not None:
            return None
        i += 1
        time.sleep(1)

    print('check_interrupt: True')
    while True:
        hora = check_hora()
        if hora:
            return 'hora'

        time.sleep(3)
        
    
# for i in range(10):
#     set_screenshot(f'./logs/20260614_123432/000{i}.jpg')
#     is_hora()
# set_screenshot('./imgs/hora_2.jpg')
# bool = is_hora()
# print(bool)