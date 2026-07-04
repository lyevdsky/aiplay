windows 安装 gpu 版本 torch
pip uninstall torch torchvision -y
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

yolo
python setup_dataset.py # 创建dataset original 图片
python augment.py # 数据增强
python split_val.py # 抽选验证训练效果用的数据

yolo 训练命令
yolo classify train model=yolov8n-cls.pt data=./dataset epochs=50 imgsz=160 batch=64 device=0 name=mahjong


