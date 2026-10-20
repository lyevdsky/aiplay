import os
import sys
import threading

import cv2

from util import timed
from kurumi.debug.recorder import get_recorder

# ── 帧源（三选一，按优先级）────────────────────────────────────
#   1. set_debug_screenshot(path)  固定返回一张图，调试单帧用
#   2. set_replay_folder(folder)   从文件夹按文件名顺序逐张取帧（视频请先用
#                                  video_to_frames.py 切成文件夹）
#   3. 都没设                      生产：摄像头(dxcam)最新帧
REPLAY_FOLDER = './frames/meld_self_kakan_0s-188.15s_50ms'   # 置 None 则走摄像头

SHOW_SCREENSHOW = False

_debug_screenshot = None
_replay_files = []
_cursor = 0                       # 回放游标：下一次取帧要读的序号
_cursor_lock = threading.Lock()   # 多线程同时取帧时，保证「读序号 + 推进」是原子的

_camera = None
_camera_lock = threading.Lock()


def set_debug_screenshot(path):
    global _debug_screenshot
    _debug_screenshot = cv2.imread(path)
    print('设置了DEBUG screenshot: ', path)


def set_replay_folder(folder):
    """指定帧文件夹，之后每次取帧按文件名顺序返回下一张；取完返回 None。
    传 None 退出回放。"""
    global _replay_files, _debug_screenshot, _cursor
    with _cursor_lock:
        _debug_screenshot = None
        _cursor = 0
        if folder is None:
            _replay_files = []
            return
        _replay_files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith((".jpg", ".png"))
        )
    print(f"replay: 载入 {len(_replay_files)} 张图片，来自 {folder}")

def replay_progress():
    """(已取帧数, 总帧数)，非回放模式为 (0, 0)。"""
    return _cursor, len(_replay_files)

def _get_camera():
    global _camera
    if _camera is None:
        with _camera_lock:
            if _camera is None:
                if sys.platform != "win32":
                    raise RuntimeError('没有可用帧源：非 Windows 无摄像头，请 set_replay_folder(...)')
                import dxcam
                cam = dxcam.create(output_color="BGR")
                cam.start(target_fps=60)
                _camera = cam
    return _camera


def _read_source():
    """统一取帧入口。回放：返回游标处的帧并推进；生产：摄像头最新帧。"""
    global _cursor
    if _debug_screenshot is not None:
        return _debug_screenshot
    if _replay_files:
        with _cursor_lock:
            if _cursor >= len(_replay_files):
                return None                      # 回放结束
            path = _replay_files[_cursor]
            _cursor += 1
        return cv2.imread(path)                  # 解码放锁外
    with timed('get_latest_frame'):
        return _get_camera().get_latest_frame()


def get_screenshot(region=None, save=0):         # save 参数保留以兼容旧调用，已无作用
  with timed('get_screenshot(总)'):
    shot = _read_source()
    frame = sys._getframe(1)
    caller_info = f"{frame.f_code.co_name}_L{frame.f_lineno}"
    get_recorder().on_frame(shot, caller_info)   # 唯一的帧登记点：所有线程取的帧都有全局 fid

    if shot is None or shot is False:
        return None

    if region is not None:
        x, y, w, h = region

        if SHOW_SCREENSHOW:
            img = shot.copy()
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 1)
            cv2.namedWindow("get_screenshot", cv2.WINDOW_NORMAL)
            cv2.imshow('get_screenshot', img)
            cv2.waitKey(1)

        return shot[y:y + h, x:x + w]

    if SHOW_SCREENSHOW:
        cv2.imshow('get_screenshot', shot)
        cv2.waitKey(1)

    return shot

if REPLAY_FOLDER:
    set_replay_folder(REPLAY_FOLDER)
