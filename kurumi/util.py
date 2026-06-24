import time
from typing import Any, Callable, Optional

import cv2
import numpy as np
import pytesseract
import asyncio
import ddddocr

ocr = ddddocr.DdddOcr(show_ad=False)
def ocr_digits(roi):
    _, encoded = cv2.imencode('.png', roi)
    result = ocr.classification(encoded.tobytes())
    result = result.replace('o', '0').replace('O', '0').replace('l', '1').replace('I', '1')
    digits = ''.join(c for c in result if c.isdigit())
    return int(digits) if digits.isdigit() else digits

def compute_mask_ratio(img, hsv):
    _hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(_hsv, hsv[0], hsv[1])
    pixel_count = cv2.countNonZero(mask)
    total_pixels = mask.shape[0] * mask.shape[1]
    percentage = pixel_count / total_pixels
    return percentage

def find_contour(img, hsv, min_area = 500, debug = False):
    imghsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hsvlist = [hsv]
    if isinstance(hsv[0], list):
        hsvlist = hsv
    else:
        hsvlist = [hsv]
    mask = None
    for _hsv in hsvlist:
        if mask is None:
            mask = cv2.inRange(imghsv, _hsv[0], _hsv[1])
        else:
            mask = cv2.bitwise_or(mask, cv2.inRange(imghsv, _hsv[0], _hsv[1]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cs = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 1300:  # 过滤太小的
            cs.append(cnt)

    if debug:
        imgcopy = img.copy()
        cv2.drawContours(imgcopy, cs, -1, (0, 255, 0), 2)
        cv2.imshow('find_contour_mask', mask)
        cv2.imshow('find_contour', imgcopy)
        cv2.waitKey(0)

    return cs

def filter_cyan(img, hsv):
    lower, upper = hsv
    _hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(_hsv, lower, upper)
    return mask

def has_template(image, template, threshold=0.8, hsv = None, debug = False):
    if hsv is not None:
        image = filter_cyan(image, hsv)
        template = filter_cyan(template, hsv)
        method = cv2.TM_CCORR_NORMED
        result = cv2.matchTemplate(image, template, method)
    else:
        method = cv2.TM_CCOEFF_NORMED
        result = cv2.matchTemplate(image, template, method)

    _, max_val, _, _ = cv2.minMaxLoc(result)

    if debug:
        cv2.imshow('has_template_image', image)
        cv2.imshow('has_template_template', template)
        print('has_template_max_val: ', max_val)
        cv2.waitKey(0)

    return max_val >= threshold

def to_black_on_white(roi):
    """将任意图片转成白底黑字"""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 判断是否需要反转：如果黑色像素多于白色，说明是深底浅字
    black_pixels = np.sum(binary == 0)
    white_pixels = np.sum(binary == 255)
    if black_pixels > white_pixels:
        binary = cv2.bitwise_not(binary)
    

    return binary


i = 0
def ocr_digits2(roi, min_area=100, debug = False):
    global i
    roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    # 如果已经是灰度图就不用转换
    if len(roi.shape) == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 反转：黑字变白字，才能用connectedComponents分析字的连通域
    inverted = cv2.bitwise_not(binary)
    # 连通组件分析，过滤小区域噪点
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    
    clean = np.zeros_like(binary)
    for label in range(1, num_labels):  # 0是背景跳过
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean[labels == label] = 255

    # 再反转回白底黑字给Tesseract
    result = cv2.bitwise_not(clean)
    if debug:
        cv2.imshow(f'ocr {i}', result)
        i += 1
        cv2.waitKey(0)

    config = "--psm 13 -c tessedit_char_whitelist=0123456789"

    numstr = pytesseract.image_to_string(result, config=config).strip()

    return int(numstr) if numstr.isdigit() else numstr


def concat_images_horizontal(images, gap=10, bg_color=(255,255,255), debug = False):
    """
    水平拼接图片，顶部对齐，图片间间隔gap像素。
    images: list of numpy arrays (H,W) or (H,W,C)
    gap: int, 间隔像素
    bg_color: tuple, 背景颜色BGR
    """
    # 确保所有图片为彩色（3通道）以便拼接
    imgs_rgb = []
    max_h = 0
    for img in images:
        if len(img.shape) == 2:  # 灰度
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:  # RGBA，可以转为BGR或保留？简单转为BGR
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        imgs_rgb.append(img)
        h, w = img.shape[:2]
        if h > max_h:
            max_h = h

    total_w = sum(img.shape[1] for img in imgs_rgb) + gap * (len(imgs_rgb)-1)
    canvas = np.full((max_h, total_w, 3), bg_color, dtype=np.uint8)

    x_offset = 0
    for img in imgs_rgb:
        h, w = img.shape[:2]
        canvas[0:h, x_offset:x_offset+w] = img  # 顶部对齐
        x_offset += w + gap

    if debug:
        cv2.imshow("拼接结果", canvas)
        cv2.waitKey()
    return canvas

def crop_min_rect(image, hsv):
    img_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(img_hsv, hsv[0], hsv[1])

    # 找mask中非零像素的边界
    cv2.imshow('image', image)
    print(hsv)
    cv2.imshow('mask', mask)
    cv2.waitKey(0)
    coords = np.where(mask > 0)  # 返回 (行索引数组, 列索引数组)
    if len(coords[0]) > 0:
        y_min, y_max = coords[0].min(), coords[0].max()
        x_min, x_max = coords[1].min(), coords[1].max()

        # 裁剪原图
        cropped = image[y_min:y_max+1, x_min:x_max+1]
        return cropped

import functools

# 待函数返回结果稳定后才返回值，用于screenshot分析的相关函数
def stable_func(func, stable_count=2, debug=False):
    """
    包装函数：连续 stable_count 次调用返回相同结果后才返回该结果，
    否则返回 None。忽略调用参数，所有调用共享状态。
    """
    # 使用列表存储最近一次结果和连续次数（闭包变量）
    last_result = None
    consecutive = 0

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        nonlocal last_result, consecutive
        result = func(*args, **kwargs)
        if debug:
            print('stable_func result: ', result)
        if consecutive == 0:
            # 第一次调用
            last_result = result
            consecutive = 1
            return None
        else:
            if result == last_result:
                consecutive += 1
                if consecutive >= stable_count:
                    # 达到稳定，返回结果并重置状态（可以决定是否保留）
                    # 这里重置，以便后续重新开始
                    last_result = None
                    consecutive = 0
                    return result
                else:
                    return None
            else:
                # 结果不一致，重置计数
                last_result = result
                consecutive = 1
                return None

    return wrapper

def polling(
    sync_func: Callable[..., Any],
    interval: float,
    timeout: Optional[float],  # 支持 None 表示永不超时
):
    """
    轮询函数。
    
    :param sync_func: 同步函数，返回非 None 值时视为有结果
    :param interval: 每次轮询的间隔秒数
    :param timeout: 超时秒数
    :return: 函数结果
    """
    elapsed = 0.0
    while timeout is None or elapsed < timeout:
        result = sync_func()
        if result is not None:
            return result
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f'轮询 {sync_func.__name__} 超时没有结果')

def create_polling_sync(
    sync_func: Callable[..., Any],
    interval: float,
    timeout: Optional[float],  # 支持 None 表示永不超时
) -> Callable[..., Any]:

    """
    创建一个同步轮询函数。
    
    :param sync_func: 同步函数，返回非 None/False 值时视为有结果
    :param interval: 每次轮询的间隔秒数
    :param timeout: 超时秒数
    :return: 同步函数
    """
    def polling_func(*args, **kwargs):
        elapsed = 0.0
        while timeout is None or elapsed < timeout:
            result = sync_func(*args, **kwargs)
            if result is not None:
                return result
            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(f'轮询 {sync_func.__name__} 超时没有结果')
    
    return polling_func

def create_polling_async(
    sync_func: Callable[..., Any],
    interval: float,
    timeout: Optional[float]  # 支持 None 表示永不超时
) -> Callable[..., Any]:

    """
    创建一个异步轮询函数。
    
    :param sync_func: 同步函数，返回非 None/False 值时视为有结果
    :param interval: 每次轮询的间隔秒数
    :param timeout: 超时秒数
    :return: 异步函数
    """
    async def polling_func(*args, **kwargs):
        elapsed = 0.0
        while timeout is None or elapsed < timeout:
            result = sync_func(*args, **kwargs)
            if result is not None:
                return result
            await asyncio.sleep(interval)
            elapsed += interval
        raise TimeoutError(
            f"轮询超时：{timeout} 秒内未获得有效结果"
        )
    
    return polling_func


# img = cv2.imread('./imgs/kyokunum_1.png')
# cropped = crop_min_rect(img, [(0, 0, 130), (180, 255, 255)])
# cv2.imshow('cropped', cropped)
# cv2.imwrite('cropped.png', cropped)
# cv2.waitKey(0)