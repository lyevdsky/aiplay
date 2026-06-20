# predict.py
from ultralytics import YOLO
import cv2

model = YOLO("../runs/classify/mahjong2/weights/best.pt")

def predict_tile(img):
    """
    img: OpenCV读取的图片 (numpy数组, BGR格式)
    返回: (牌名, 置信度)
    """
    result = model.predict(img, verbose=False)[0]
    top1 = result.probs.top1
    name = result.names[top1]
    conf = result.probs.top1conf.item()

    if name == "none":
        return None, conf  # 识别为干扰物，过滤掉
    return name, conf

# 测试
img = cv2.imread("./hard_examples/z5/hard_001.png")
name, conf = predict_tile(img)
print(f"识别结果: {name}  置信度: {conf:.2%}")