import os

import cv2
from collections import deque
from datetime import datetime
from pynput import keyboard

SHOW_SCREENSHOW = True
img_q = deque(maxlen=10)
test_screenshots = []

cap = cv2.VideoCapture("./video/meld_next_ankan.mp4")
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）
t = -1
video_start_s = 0
# 105950
def video_capture(s = None):
    global t
    t += 1
    ms = video_start_s + t * 50 if s is None else s * 1000
    cap.set(cv2.CAP_PROP_POS_MSEC, ms)   # 跳转到 t 秒（毫秒）
    ret, frame = cap.read()
    if ret:
        # 顶部填充8像素宽
        # img = cv2.copyMakeBorder(frame, 8, 0, 0, 0,
        # cv2.BORDER_CONSTANT, value=(255,255,255))
        img = frame
        # 处理 frame
        return img
    return False

# img = video_capture(105.950)
# cv2.imwrite('yolo_error_1m_2.png', img)

def screenshot():
    global t
    if len(test_screenshots) > 0:
        t = t + 1 if t < len(test_screenshots) - 1 else len(test_screenshots) - 1
        return test_screenshots[t]
    
    t += 1
    img = video_capture()
    # img = cv2.imread(f'./screenshots/{t}.png')
    img_q.append(img)
    return img

def set_screenshot(paths):
    if isinstance(paths, list):
        for path in paths:
            test_screenshots.append(cv2.imread(path))
    elif isinstance(paths, str):
        img = cv2.imread(paths)
        test_screenshots.append(img)
import time

def get_screenshot(region = None, cache_ms=200):
    # 使用函数属性保存缓存状态（也可以使用全局变量，但属性更整洁）
    if not hasattr(get_screenshot, "_last_screenshot"):
        get_screenshot._last_screenshot = None
        get_screenshot._last_time = 0.0

    now = time.time()
    # 检查是否有有效缓存
    if (cache_ms is not None and
        get_screenshot._last_screenshot is not None and 
        (now - get_screenshot._last_time) * 1000 < cache_ms):
        shot = get_screenshot._last_screenshot
    else:
        shot = screenshot()

    if region is not None:
        x,y,w,h = region
        
        if SHOW_SCREENSHOW:
            img = shot.copy()
            cv2.rectangle(img, (x, y), (x + w, y+h), (0,0,255), 1)
            cv2.imshow('get_screenshot', img)
            cv2.waitKey(10)

        return shot[y:y+h,x:x+w]

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

# for i in range(100):
#     img = video_capture()
#     img_with_border = cv2.copyMakeBorder(img, 8, 0, 0, 0,
#                                      cv2.BORDER_CONSTANT, value=(255,255,255))

#     cv2.imshow('s', img_with_border)
    
#     cv2.imwrite(f'./video/{i}.png', img_with_border)

#     cv2.waitKey(0)
#     cv2.destroyAllWindows()



# def on_press(key):
#     if key == keyboard.Key.f1:
#         print("f1")
#         save_img_q()

# # 启动监听器
# with keyboard.Listener(on_press=on_press) as listener:
#     listener.join()