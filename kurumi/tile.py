import cv2
from config import TILE_WHILE_HSV, WHILE_HSV, IS_DEV
from util import find_contour
from ultralytics import YOLO

MOCK = False
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
        if name == 'z5':
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, TILE_WHILE_HSV[0], TILE_WHILE_HSV[1])
            ratio = cv2.countNonZero(mask) / (w * h)
            if ratio < 0.8:
                print('误检测为z5', ratio)
                return None
        return name[::-1]
    
    return None

# 图片转向成正的纵向
def normalize_direction(tileimg, player):
    h, w = tileimg.shape[:2]

    if player == 'self':
        if w / h > 1.5:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_CLOCKWISE)
            direction = 'next'
        else:
            direction = 'self'
    elif player == 'next':
        if w / h < 1.8:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_180)
            direction = 'across'
        else:
            direction = 'next'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_CLOCKWISE)
    elif player == 'across':
        if w / h > 1.5:
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_COUNTERCLOCKWISE)
            direction = 'prev'
        else:
            direction = 'across'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_180)
    else:
        if w / h < 1.5:
            direction = 'self'
        else:
            direction = 'prev'
            tileimg = cv2.rotate(tileimg, cv2.ROTATE_90_COUNTERCLOCKWISE)
    
    return tileimg, direction

def check_tile(img, player = 'self', min_area=1500, threshold=0.8, return_dict = False, autocrop = True, debug=False):
    if autocrop:
        # 先找亮白，再尝试模切的灰白。避免找的牌面矩形不对，导致normalize_direction判断有误
        cs = find_contour(img, WHILE_HSV, min_area)
        if len(cs) == 0:
            cs = find_contour(img, TILE_WHILE_HSV, min_area)
            if len(cs) == 0:
                return None

        x,y,w,h = cv2.boundingRect(cs[0])
        tileimg = img[y:y+h,x:x+w]
    else:
        tileimg = img

    normalized_img, direction = normalize_direction(tileimg, player)

    if debug:
        cv2.imshow('check_tile', normalized_img)
        cv2.waitKey(0)
        cv2.destroyWindow('check_tile')

    tile = predict_tile(normalized_img, threshold, debug=debug)
    if tile is None:
        return None

    if return_dict:
        return {
            'tile': tile,
            'region': (x,y,w,h),
            'contour': cs[0],
            'direction': direction
        }

    return tile

def check_tiles(img, player = 'self', min_area=1500, threshold=0.8, debug=False):
    cs = find_contour(img, WHILE_HSV, min_area)

    result = []
    for c in cs:
        x,y,w,h = cv2.boundingRect(c)
        tileimg = img[y:y+h,x:x+w]
        normalized_img, direction = normalize_direction(tileimg, player)

        if debug:
            print(f'width: {w}, height: {h}')
            cv2.imshow('check_tile', normalized_img)
            cv2.waitKey(0)
            cv2.destroyWindow('check_tile')

        tile = predict_tile(normalized_img, threshold, debug=debug)

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