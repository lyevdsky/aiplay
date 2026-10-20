"""把视频的 [START_S, END_S] 区间每隔 STEP_MS 取一帧，无损 PNG 存进一个文件夹。

用法：改下面「参数」区的变量，然后直接运行  python video_to_frames.py
之后 screenshot.py 里把 REPLAY_FOLDER 指向输出文件夹即可。

输出：
    <OUT_DIR>/000000.png 000001.png ...   序号即回放顺序
    <OUT_DIR>/frames.json                 来源视频、参数、每帧在视频中的时间戳(ms)
"""
import json
import os

import cv2

# ───────────────────────── 参数（在这里改）─────────────────────────
VIDEO = "./video/meld_self_kakan.mp4"   # 视频路径
START_S = 0.0                            # 起点（秒）
END_S = None                             # 终点（秒），None = 到视频结尾
STEP_MS = 50.0                          # 取帧间隔（毫秒），建议 = config.POLLING_INTERVAL * 1000
OUT_DIR = None                           # 输出文件夹，None = ./frames/<视频名>_<起>s-<止>s_<间隔>ms
OVERWRITE = False                        # 输出文件夹非空时，True = 清掉旧 png/json 重来
# ──────────────────────────────────────────────────────────────────


def extract_frames(video, start_s=0.0, end_s=None, step_ms=100.0, out_dir=None, overwrite=False):
    """返回输出文件夹路径。取帧规则：从 start 起，每次取【时间戳 >= 下一个目标时刻】
    的第一帧，目标时刻每次 +step_ms；全程顺序解码，只在起点 seek 一次。"""
    if step_ms <= 0:
        raise ValueError('STEP_MS 必须 > 0')
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise FileNotFoundError(f'打不开视频: {video}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if not fps or fps <= 0:
        raise RuntimeError('读不到视频 fps')
    duration_s = total / fps
    end_s = duration_s if end_s is None else min(end_s, duration_s)
    if start_s >= end_s:
        raise ValueError(f'START_S({start_s}s) 必须小于 END_S({end_s}s)')

    if out_dir is None:
        stem = os.path.splitext(os.path.basename(video))[0]
        out_dir = os.path.join('./frames', f'{stem}_{start_s:g}s-{end_s:g}s_{step_ms:g}ms')
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        if not overwrite:
            raise FileExistsError(f'{out_dir} 非空（回放按文件夹内全部图片取帧，不能混入旧帧）；'
                                  f'换 OUT_DIR 或把 OVERWRITE 设为 True')
        for f in os.listdir(out_dir):
            if f.lower().endswith(('.png', '.json')):
                os.remove(os.path.join(out_dir, f))
    os.makedirs(out_dir, exist_ok=True)

    start_ms, end_ms = start_s * 1000.0, end_s * 1000.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start_ms)
    idx = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES)))     # seek 后实际落点
    next_t = start_ms
    timestamps = []
    n = 0
    while True:
        if not cap.grab():                                  # 只取不解码，便宜
            break
        t = idx * 1000.0 / fps
        idx += 1
        if t > end_ms:
            break
        if t + 1e-6 >= next_t:
            ok, frame = cap.retrieve()                      # 只解码要保存的帧
            if not ok:
                break
            # PNG 无损：存下的就是解码出的原始像素
            cv2.imwrite(os.path.join(out_dir, f'{n:06d}.png'), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            timestamps.append(round(t, 2))
            n += 1
            next_t += step_ms
            if n % 100 == 0:
                print(f'  已保存 {n} 帧 (视频 {t / 1000:.1f}s)')
    cap.release()

    with open(os.path.join(out_dir, 'frames.json'), 'w', encoding='utf-8') as f:
        json.dump({'video': video, 'start_s': start_s, 'end_s': end_s, 'step_ms': step_ms,
                   'fps': fps, 'count': n, 'timestamps_ms': timestamps}, f, ensure_ascii=False)
    print(f'完成：{n} 帧 -> {out_dir}')
    return out_dir


if __name__ == '__main__':
    extract_frames(VIDEO, START_S, END_S, STEP_MS, OUT_DIR, OVERWRITE)
