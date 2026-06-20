import os
import time
import cv2
from collections import deque
from datetime import datetime
from pynput import keyboard
from config import POLLING_INTERVAL
import sys

if sys.platform == "win32":
    import dxcam
    camera = dxcam.create(output_color="BGR")
    frame = camera.get_latest_frame() 
    region = (0, 0, 2560, 1440)
    camera.start(target_fps=60)

SHOW_SCREENSHOW = False
img_q = deque(maxlen=10)
_debug_screenshot = None

cap = cv2.VideoCapture("./video/kyo.mp4")
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）
# TODO 立直 跳过 overlay 位置
# {'type': 'dahai', 'actor': 2, 'pai': '2m', 'tsumogiri': False, 'meta': {'q_values': [0.97319365, 0.30731368, -6.671384, -5.8309374, -6.306546, -5.960788, -6.158166, -5.870702, -5.961959, -6.037217, -6.556838, -6.2457476, 0.7458465], 'mask_bits': 189007972454, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 41266400, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '2m', 'q_value': 0.97319365}, {'label': 'riichi', 'q_value': 0.7458465}, {'label': '3m', 'q_value': 0.30731368}, {'label': '7m', 'q_value': -5.8309374}, {'label': '5s', 'q_value': -5.870702}, {'label': '6p', 'q_value': -5.960788}, {'label': '6s', 'q_value': -5.961959}, {'label': '7s', 'q_value': -6.037217}, {'label': '7p', 'q_value': -6.158166}, {'label': '0p', 'q_value': -6.2457476}, {'label': '3p', 'q_value': -6.306546}, {'label': '0m', 'q_value': -6.556838}, {'label': '6m', 'q_value': -6.671384}]} 
def video_capture():
    video_start_ms = 0
    video_start_ms = 24000
    if not hasattr(video_capture, '_count'):
        video_capture._count = 0
        video_capture._start_time = time.time()
    if True:
        ms = video_start_ms + video_capture._count * (1000 * POLLING_INTERVAL)
        video_capture._count += 1
    else:
        ratio = 0.8
        now = time.time()
        ms = round((now - video_capture._start_time) * 1000 * ratio)

    cap.set(cv2.CAP_PROP_POS_MSEC, ms)   # 跳转到 ms 毫秒
    ret, frame = cap.read()
    if ret:
        return frame
    return False

# img = video_capture()
# cv2.imwrite('dora1_error.png', img)

def set_debug_screenshot(path):
    global _debug_screenshot
    img = cv2.imread(path)
    _debug_screenshot = img

def get_screenshot(region = None):
    if _debug_screenshot is not None:
        shot = _debug_screenshot
    else:
        # shot = video_capture()
        shot = camera.get_latest_frame()
    
    frame = sys._getframe(1)
    # TODO 不能仅保存最近10张，还应该保存关键方法调用
    caller_info = f"{frame.f_code.co_name}_L{frame.f_lineno}"
    img_q.append((shot, caller_info))

    if region is not None:
        x,y,w,h = region
        
        if SHOW_SCREENSHOW:
            img = shot.copy()
            cv2.rectangle(img, (x, y), (x + w, y+h), (0,0,255), 1)
            cv2.namedWindow("get_screenshot", cv2.WINDOW_NORMAL)
            cv2.imshow('get_screenshot', img)
            cv2.waitKey(1)

        return shot[y:y+h,x:x+w]

    if SHOW_SCREENSHOW:
        cv2.imshow('get_screenshot', shot)
        cv2.waitKey(1)

    return shot

def save_img_q(path = None):
    if path == None:
        folder_name = './logs/' + datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        folder_name = path
    os.makedirs(folder_name, exist_ok=True)

    # 2. 遍历队列，保存图片
    idx = 0
    while img_q:
        img, caller_info = img_q.popleft()   # 从左侧弹出，先进先出
        # 生成文件名，例如 0001_funcname_L42.jpg
        filename = os.path.join(folder_name, f"{idx:04d}_{caller_info}.png")
        cv2.imwrite(filename, img)
        idx += 1

    print(f"共保存 {idx} 张图片到文件夹 {folder_name}")