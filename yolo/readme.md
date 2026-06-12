windows 安装 gpu 版本 torch
pip uninstall torch torchvision -y
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

yolo 训练命令
yolo classify train model=yolov8n-cls.pt data=./dataset epochs=50 imgsz=160 batch=64 device=0 name=mahjong