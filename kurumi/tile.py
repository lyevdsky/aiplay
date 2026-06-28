from enum import Enum
import os
import cv2
import numpy as np
from config import TILE_WHILE_HSV, WHILE_HSV, IS_DEV, SAME_TILE_HIGHLIGHT_HSV
from util import find_contour, timed
from ultralytics import YOLO

class TileType(Enum):
    Hand = 'hand'
    Kawa = 'kawa'
    Meld = 'meld'
    Dora = 'dora'

MOCK = False

# 上一张误检测保存的图片，用于去重避免重复保存
_last_error_img = None

def save_error_img(img, prefix='z5'):
    global _last_error_img
    # 与上一张误检测图片比对，尺寸一致且像素完全相同则跳过
    if (_last_error_img is not None
            and _last_error_img.shape == img.shape
            and np.array_equal(_last_error_img, img)):
        return
    _last_error_img = img.copy()

    save_dir = './logs/error'
    os.makedirs(save_dir, exist_ok=True)
    import time
    path = os.path.join(save_dir, f'{prefix}_{int(time.time() * 1000)}.png')
    cv2.imwrite(path, img)
    return path
    
if IS_DEV:
    model = None
else:
    model = YOLO("./ref/yolo/best.pt")

def get_model():
    global model
    if model is None:
        # model = YOLO("/Users/weilong/code/mjai/mahjong-game/runs/classify/mahjong/weights/best.pt")
        model = YOLO("./ref/yolo/best.pt")
    return model

# 再次校验5z
def check_5z(img):
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, TILE_WHILE_HSV[0], TILE_WHILE_HSV[1])
    ratio = cv2.countNonZero(mask) / (w * h)
    mask2 = cv2.inRange(hsv, SAME_TILE_HIGHLIGHT_HSV[0], SAME_TILE_HIGHLIGHT_HSV[1])
    ratio2 = cv2.countNonZero(mask2) / (w * h)
    if ratio < 0.8 and ratio2 < 0.8:
        # print('误检测为z5', ratio)
        save_error_img(img, prefix='z5')
        return False

    return True

def predict_tile(img, threshold = 0.8, debug=False):
    # 检查图片尺寸是否合理
    h, w = img.shape[:2]
    if w < 30 or h < 30:
        return None  # 图片太小
    # if w / h < 0.32:
    #     print('宽高比过于夸张')
    #     return None # 宽高比过于夸张
    """
    img: OpenCV读取的图片 (numpy数组, BGR格式)
    返回: (牌名, 置信度)
    """
    if MOCK:
        return "s1"
    result = get_model().predict(img, verbose=False)[0]
    top1 = result.probs.top1
    name = result.names[top1]
    conf = result.probs.top1conf.item()

    # if conf > 0.7 and conf < 0.8:
    #     cv2.imwrite('./logs/error/1.png', img)
    if debug:
        print(f'predict_tile: ({name},{conf:.2f})')
        if conf > 0.7 and conf < 0.8:
            cv2.imwrite('./logs/error/1.png', img)

    if conf > threshold:
        return name[::-1]
    
    return None

TILE_SHAPE_RULE = {
    'self': {
        'hand': {
            'area': (20000, 23000),
            'wh_ratio': (0.7, 0.8)
        },
        'kawa': {
            'area': (5000, 7000),
            'wh_ratio': (0.9, 1.2),
            'rotated_wh_ratio': (1.8, 2.3),
        },
        'meld': {
            'area': (7000, 10000),
            'wh_ratio': (0.9,1.6),
            'rotated_wh_ratio': (1.7, 2.0),
        },
        'dora': {
            'area': (4000, 6000),
            'wh_ratio': (0.7, 0.8)
        }
    },
    'next': {
        'kawa': {
            'area': (3500, 5500),
            'rotated_wh_ratio': (1.0, 1.4),
            'wh_ratio': (1.8, 2.5)
        },
        'meld': {
            'area': (3000, 5500), # (3000, ?)
            'rotated_wh_ratio': (1.2, 1.8),
            'wh_ratio': (1.2, 2.5) #(?, 2.5)
        }
    },
    'across':{
        'kawa': {
            'area': (4000, 6000),
            'wh_ratio': (1.2, 1.45),
            'rotated_wh_ratio': (1.8, 2.5),
        },
        'meld': {
            'area': (2600,4500), #(2600, ?)
            'wh_ratio': (1.2, 1.6),
            'rotated_wh_ratio': (1.8, 2.5),
        }
    },
    'prev': {
        'kawa': {
            'area': (3500, 5500),
            'rotated_wh_ratio': (1.0, 1.4),
            'wh_ratio': (1.8, 2.5)
        },
        'meld': {
            'area': (5000, 9500),
            'wh_ratio': (1.8, 2.5),
            'rotated_wh_ratio': (1.0, 1.4),
        }
    },
}
def get_shape_rule(player, type):
    key = type.value if isinstance(type, TileType) else type
    return TILE_SHAPE_RULE.get(player, {}).get(key)


# 根据 player/type 从规则表取最小面积，作为轮廓检测的 min_area
def get_min_area(player, type):
    rule = get_shape_rule(player, type)
    return rule['area'][0] if rule else 0


def validate_tileimg(tileimg, player, type):
    h, w = tileimg.shape[:2]

    rule = get_shape_rule(player, type)
    if rule is None:
        return False

    area = h * w
    area_min, area_max = rule['area']
    if not (area_min <= area <= area_max):
        return False

    ratio = w / h
    for key in ('wh_ratio', 'rotated_wh_ratio'):
        if key in rule:
            lo, hi = rule[key]
            if lo <= ratio <= hi:
                return True

    return False


# w/h 是否落在该 player/type 的 rotated_wh_ratio 区间内（即牌被横置/旋转）
def is_rotated_ratio(player, type, ratio):
    rule = get_shape_rule(player, type)
    if not rule or 'rotated_wh_ratio' not in rule:
        return False
    lo, hi = rule['rotated_wh_ratio']
    return lo <= ratio <= hi

# 图片转向成正的纵向
def normalize_direction(tileimg, player, type=TileType.Kawa):
    h, w = tileimg.shape[:2]
    rotated = is_rotated_ratio(player, type, w / h)

    if player == 'self':
        if rotated:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_CLOCKWISE)
            direction = 'next'
        else:
            direction = 'self'
    elif player == 'next':
        if rotated:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_180)
            direction = 'across'
        else:
            direction = 'next'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_CLOCKWISE)
    elif player == 'across':
        if rotated:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_COUNTERCLOCKWISE)
            direction = 'prev'
        else:
            direction = 'across'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_180)
    else:
        if rotated:
            direction = 'self'
        else:
            direction = 'prev'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return tileimg, direction

def check_tile(img, player = 'self', type=TileType.Kawa, threshold=0.8, return_dict = False, autocrop = True, debug=False):
  with timed('check_tile'):
    min_area = get_min_area(player, type)
    if autocrop:
        # 先找亮白，再尝试模切的灰白。避免找的牌面矩形不对，导致normalize_direction判断有误
        cs = find_contour(img, WHILE_HSV, min_area)
        if len(cs) == 0 and type == TileType.Kawa:
            cs = find_contour(img, TILE_WHILE_HSV, min_area)
        if len(cs) == 0 and type != TileType.Hand:
            cs = find_contour(img, SAME_TILE_HIGHLIGHT_HSV, min_area)
        if len(cs) == 0:
            return None

        x,y,w,h = cv2.boundingRect(cs[0])
        tileimg = img[y:y+h,x:x+w]
    else:
        tileimg = img

    valid = validate_tileimg(tileimg, player, type)
    # print('valid: ', valid)
    if not valid:
        return None

    normalized_img, direction = normalize_direction(tileimg, player, type)

    if debug:
        cv2.imshow('check_tile', normalized_img)
        cv2.waitKey(0)
        cv2.destroyWindow('check_tile')

    tile = predict_tile(normalized_img, threshold, debug=debug)
    if tile is None:
        return None

    if tile == '5z' and not check_5z(normalized_img):
        return None

    if return_dict:
        return {
            'tile': tile,
            'region': (x,y,w,h),
            'contour': cs[0],
            'direction': direction
        }

    return tile

def check_tiles(img, player = 'self', type=TileType.Meld, threshold=0.8, debug=False):
    min_area = get_min_area(player, type)
    cs = find_contour(img, WHILE_HSV, min_area, debug=debug)
    cs2 = find_contour(img, SAME_TILE_HIGHLIGHT_HSV, min_area, debug=debug)

    result = []
    for c in (cs + cs2):
        x,y,w,h = cv2.boundingRect(c)
        tileimg = img[y:y+h,x:x+w]

        valid = validate_tileimg(tileimg, player, type)
        if not valid:
            continue

        normalized_img, direction = normalize_direction(tileimg, player, type)

        if debug:
            print(f'width: {w}, height: {h}')
            cv2.imshow('check_tile', normalized_img)
            cv2.waitKey(0)
            # cv2.destroyWindow('check_tile')

        tile = predict_tile(normalized_img, threshold, debug=debug)

        if tile == '5z' and not check_5z(normalized_img):
            continue

        if tile is not None:
            result.append({
                'tile': tile,
                'region': (x,y,w,h),
                # 'contour': c,
                'direction': direction
            })

    return result


# img = cv2.imread('./logs/error/yolo_6p2.png')
# predict_tile(img, debug=True)
# x,y,w,h = (1612,433,104,78)
# img = img[y:y+h,x:x+w]
# check_tile(img, 'next', debug=True)