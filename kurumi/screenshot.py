import os
import time
import cv2
import threading
from collections import deque
from datetime import datetime
from config import IS_DEV, POLLING_INTERVAL
from util import timed   # 临时性能埋点
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

cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
# cv2.VideoCapture(底层 ffmpeg)非线程安全：main 与 watcher 并发 set+read
# 会踩坏解码器状态导致崩溃，故 seek+read 必须整体串行
_cap_lock = threading.Lock()
# cap = cv2.VideoCapture("./video/meld_self_kakan.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps   # 视频总时长（秒）

VIDEO_START_MS = 0       # dev 视频以这一毫秒处作为游标 0
# VIDEO_START_MS = 129000
VIDEO_END_MS = None      # dev 视频跑到这一毫秒即视作结束（None=跑到视频真正结尾）

# ── 单一游标 ──────────────────────────────────────────────────
# 全局只有一个游标，代表"当前这一帧"。任何 reader 取帧（_read_source）都只读
# 当前游标指向的帧，不区分身份、不等待、不自动推进。游标的前进由 advance_cursor
# 单独负责，并只在 main 侧的 get_screenshot 里调用——于是视频快慢只跟 main 取帧
# 节奏挂钩，与墙钟、调试暂停无关；watcher 只是顺手读当前帧，读到重复也无妨。
_cursor = 0                   # 当前帧序号（仅 replay 用作文件下标）
# 一个 POLLING_INTERVAL 对应跳过多少原生帧（按顺序 grab 跳过，不随机 seek）
_FRAME_STEP = max(1, round(POLLING_INTERVAL * fps))

# 模块加载时唯一一次 seek：定位到起点并读入首帧；之后 advance_cursor 全程顺序解码。
cap.set(cv2.CAP_PROP_POS_MSEC, VIDEO_START_MS)
_ret, _current_frame = cap.read()   # dev 视频当前帧（False=播放结束）
if not _ret:
    _current_frame = False

def advance_cursor():
    """前进一步：顺序跳过 _FRAME_STEP 帧（grab 不解码，便宜），read 出目标帧。
    全程不随机 seek。仅由 main 侧 get_screenshot 调用。"""
    global _cursor, _current_frame
    _cursor += 1
    # 用于断点
    if (_cursor * POLLING_INTERVAL) > 130:
        pass
    with _cap_lock:
        with timed('video_advance'):
            for _ in range(_FRAME_STEP - 1):
                cap.grab()                 # 跳过中间帧
            ret, frame = cap.read()        # 只解码这一帧
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    # 到达设定终点即当作视频结束（返回 False），省得每次都跑完整段视频
    if VIDEO_END_MS is not None and pos_ms >= VIDEO_END_MS:
        _current_frame = False
        return
    _current_frame = frame if ret else False

def set_debug_screenshot(path):
    global _debug_screenshot
    img = cv2.imread(path)
    _debug_screenshot = img
    print('设置了DEBUG screenshot: ', path)

# 复现用：从 logs/xxx 文件夹按文件名顺序逐张读取，所有 reader 共用上面的单游标。
_replay_files = []

def set_replay_folder(folder):
    """指定一个 logs 下保存过的文件夹，之后取帧按游标位置返回其中的图片。"""
    global _replay_files, _debug_screenshot, _cursor
    _replay_files = sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".png"))
    )
    _debug_screenshot = None
    _cursor = 0                  # 换帧源，游标从头开始
    print(f"replay: 载入 {len(_replay_files)} 张图片，来自 {folder}")

# set_replay_folder('./logs/test2')
set_replay_folder('./logs/20260708_220907')

def _read_source():
    """统一取帧入口：只读当前游标指向的那一帧，不区分 reader、不推进游标。
    dev/replay 下全局共用一个游标；生产直接取摄像头最新帧。"""
    if _debug_screenshot is not None:
        return _debug_screenshot
    if not IS_DEV and not _replay_files:
        with timed('get_latest_frame'):
            frame = camera.get_latest_frame()
        return frame
    if _replay_files:
        return cv2.imread(_replay_files[_cursor]) if _cursor < len(_replay_files) else None
    return _current_frame

def get_screenshot(region = None, save = 0):
  with timed('get_screenshot(总)'):
    shot = _read_source()
    if IS_DEV:
        advance_cursor()   # main 侧每取一帧推进游标，watcher 读到的"当前帧"随之前进
    frame = sys._getframe(1)
    caller_info = f"{frame.f_code.co_name}_L{frame.f_lineno}"
    # 入队时即编码成 JPEG，大幅降低内存占用
    # ok, buf = cv2.imencode(".jpg", shot, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    # if ok:
    img_q.append((shot, caller_info))

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

def save_img_q(path = None):
    if path == None:
        folder_name = './logs/' + datetime.now().strftime("%Y%m%d_%H%M%S")
    else:
        folder_name = path
    os.makedirs(folder_name, exist_ok=True)

    # 2. 遍历队列，保存图片
    items = list(img_q)
    img_q.clear()
    saved = 0
    for idx, (img, caller_info) in enumerate(items):
        # 视频结束/取帧失败时入队的是 False/None，跳过但仍占用 idx，
        # 保证文件名下标与该帧在 img_q 中的位置（即日志里的帧号）严格对齐
        if img is None or img is False:
            continue
        # 用无损 PNG 保存，保证复现时读到的像素与 live 识别时的原始帧完全一致
        # （JPEG 有损压缩会让临界牌的轮廓/置信度发生偏移，导致复现不出 live 的识别结果）
        filename = os.path.join(folder_name, f"{idx:04d}_{caller_info}.png")
        # img.tofile(filename)
        cv2.imwrite(filename, img)
        saved += 1

    print(f"共保存 {saved} 张图片到文件夹 {folder_name}")

    # 3. 保存通过 save 标记的快照，每个快照存到独立子文件夹
    for snap_idx, (snap_caller, shots) in enumerate(saved_snapshots.items()):
        sub_folder = os.path.join(folder_name, f"snapshot_{snap_idx:02d}_{snap_caller}")
        os.makedirs(sub_folder, exist_ok=True)
        for i, (img, caller_info) in enumerate(shots):
            # 同样用无损 PNG，确保快照与 live 原始帧逐像素一致
            filename = os.path.join(sub_folder, f"{i:04d}_{caller_info}.png")
            cv2.imwrite(filename, img)
            # img.tofile(filename)
        print(f"快照保存 {len(shots)} 张图片到文件夹 {sub_folder}")

    saved_snapshots.clear()