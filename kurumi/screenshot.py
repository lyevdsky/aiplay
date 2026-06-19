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

SHOW_SCREENSHOW = True
img_q = deque(maxlen=10)
_debug_screenshot = None

cap = cv2.VideoCapture("./video/full.mp4")
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）

def video_capture():
    video_start_ms = 0
    video_start_ms = 180000
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

def set_debug_screenshot(path):
    global _debug_screenshot
    img = cv2.imread(path)
    _debug_screenshot = img

def get_screenshot(region = None):
    if _debug_screenshot is not None:
        return _debug_screenshot

    shot = video_capture()
    # shot = camera.get_latest_frame()
    
    img_q.append(shot)

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

def save_img_q():
    folder_name = './logs/' + datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(folder_name, exist_ok=True)

    # 2. 遍历队列，保存图片
    idx = 0
    while img_q:
        img = img_q.popleft()   # 从左侧弹出，先进先出
        # 生成文件名，例如 0001.jpg
        filename = os.path.join(folder_name, f"{idx:04d}.jpg")
        cv2.imwrite(filename, img)
        idx += 1

    print(f"共保存 {idx} 张图片到文件夹 {folder_name}")