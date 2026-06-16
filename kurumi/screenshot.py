import os
import time
import cv2
from collections import deque
from datetime import datetime
from pynput import keyboard
import dxcam

camera = dxcam.create(output_color="BGR")
frame = camera.get_latest_frame() 
region = (0, 0, 2560, 1440)
camera.start(target_fps=60)

SHOW_SCREENSHOW = False
img_q = deque(maxlen=10)
screenshot = {
    'img': None,
    'time': 0
}

cap = cv2.VideoCapture("./video/full.mp4")
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）

def video_capture():
    # video_start_ms = 174000
    video_start_ms = 0

    if not hasattr(video_capture, '_count'):
        video_capture._count = 0
        video_capture._start_time = time.time()
    if False:
        ms = video_start_ms + video_capture._count * 50
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
# cv2.imwrite('tenpai.png', img)
# def screenshot():
#     global t
#     if len(test_screenshots) > 0:
#         t = t + 1 if t < len(test_screenshots) - 1 else len(test_screenshots) - 1
#         return test_screenshots[t]
    
#     t += 1
#     img = video_capture()
#     # img = cv2.imread(f'./screenshots/{t}.png')
#     img_q.append(img)
#     return img

def capture():
    frame = camera.get_latest_frame()
    # return video_capture()
    return frame

def set_screenshot(path):
    img = cv2.imread(path)
    screenshot['img'] = img
    screenshot['time'] = 10**18

def get_screenshot(region = None, cache_ms=50):
    now = time.time()

    # 检查是否有有效缓存
    if (cache_ms is not None and
        screenshot['img'] is not None and 
        (now - screenshot['time']) * 1000 < cache_ms):
        shot = screenshot['img']
    else:
        screenshot['img'] = capture()
        screenshot['time'] = now
        shot = screenshot['img']

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

# screenshot()
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