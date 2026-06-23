import os
import time
import cv2
from collections import deque
from datetime import datetime
from config import IS_DEV, POLLING_INTERVAL
import sys

if sys.platform == "win32":
    import dxcam
    camera = dxcam.create(output_color="BGR")
    frame = camera.get_latest_frame() 
    region = (0, 0, 2560, 1440)
    camera.start(target_fps=60)

SHOW_SCREENSHOW = False
JPEG_QUALITY = 95
img_q = deque(maxlen=500)
saved_snapshots = {}   # {caller_info: [(buf, caller_info), ...]}，同一调用点再次触发会覆盖，save_img_q 时各存为一个子文件夹
_debug_screenshot = None

cap = cv2.VideoCapture("./video/kyo.mp4")
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）

def video_capture(reader='main'):
    video_start_ms = 0
    video_start_ms = 24000
    # 每个读取者一份独立游标，互不影响（main 低频认牌、watcher 高频盯 bar）
    if not hasattr(video_capture, '_counts'):
        video_capture._counts = {}
    count = video_capture._counts.get(reader, 0)
    ms = video_start_ms + count * (1000 * POLLING_INTERVAL)
    video_capture._counts[reader] = count + 1

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

# 复现用：从 logs/xxx 文件夹按文件名顺序逐张读取。
# 每个读取者（main / watcher）各持独立游标，回放生产环境的并行取帧。
_replay_files = []
_replay_idx = {}

def set_replay_folder(folder):
    """指定一个 logs 下保存过的文件夹，之后取帧会按顺序逐张返回其中的图片。"""
    global _replay_files, _replay_idx, _debug_screenshot
    _replay_files = sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".png"))
    )
    _replay_idx = {}
    _debug_screenshot = None
    print(f"replay: 载入 {len(_replay_files)} 张图片，来自 {folder}")

def _next_replay_shot(reader='main'):
    """返回该读取者的下一张复现图片；播放完后停留在最后一张。"""
    if not _replay_files:
        return None
    cur = _replay_idx.get(reader, 0)
    idx = min(cur, len(_replay_files) - 1)
    _replay_idx[reader] = cur + 1
    return cv2.imread(_replay_files[idx])

# set_replay_folder('./logs/20260621_143003/snapshot_08_rec_dahai_L61')
# set_replay_folder('./logs/20260621_162718')

def _read_source(reader='main'):
    """统一取帧入口：按读取者身份从当前帧源取下一帧。
    生产 dxcam 非消费，replay/video 各读取者独立游标。"""
    if _debug_screenshot is not None:
        return _debug_screenshot
    if _replay_files:
        return _next_replay_shot(reader)
    if IS_DEV:
        return video_capture(reader)
    return camera.get_latest_frame()

def get_screenshot(region = None, save = 0):
    shot = _read_source('main')

    frame = sys._getframe(1)
    caller_info = f"{frame.f_code.co_name}_L{frame.f_lineno}"
    # 入队时即编码成 JPEG，大幅降低内存占用
    ok, buf = cv2.imencode(".jpg", shot, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if ok:
        img_q.append((buf, caller_info))

    if save:
        # 记录当前 img_q 中最近 save 张的快照，同一调用点会覆盖旧快照
        recent = list(img_q)[-save:]
        saved_snapshots[caller_info] = recent

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

def get_raw_frame():
    """给后台 watcher 线程用的轻量取帧：不入 img_q、不做 region 裁剪、
    不记录 caller 快照。replay/video 下持 'watcher' 独立游标，与 main 互不影响。"""
    return _read_source('watcher')

def save_img_q(path = None):
    if path == None:
        folder_name = './logs/' + datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        folder_name = path
    os.makedirs(folder_name, exist_ok=True)

    # 2. 遍历队列，保存图片
    items = list(img_q)
    img_q.clear()
    idx = 0
    for img, caller_info in items:
        # 生成文件名，例如 0001_funcname_L42.jpg
        filename = os.path.join(folder_name, f"{idx:04d}_{caller_info}.jpg")
        img.tofile(filename)
        idx += 1

    print(f"共保存 {idx} 张图片到文件夹 {folder_name}")

    # 3. 保存通过 save 标记的快照，每个快照存到独立子文件夹
    for snap_idx, (snap_caller, shots) in enumerate(saved_snapshots.items()):
        sub_folder = os.path.join(folder_name, f"snapshot_{snap_idx:02d}_{snap_caller}")
        os.makedirs(sub_folder, exist_ok=True)
        for i, (img, caller_info) in enumerate(shots):
            filename = os.path.join(sub_folder, f"{i:04d}_{caller_info}.jpg")
            img.tofile(filename)
        print(f"快照保存 {len(shots)} 张图片到文件夹 {sub_folder}")

    saved_snapshots.clear()