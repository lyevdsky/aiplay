# setup_dataset.py
import shutil
from pathlib import Path

# 配置
SRC_DIR = Path("ref")   # 改成你的原始图片文件夹路径
TRAIN_DIR = Path("dataset/train")


for img_path in sorted(SRC_DIR.glob("*.png")):
    class_name = img_path.stem  # m1, m2, p1, z1 ...
    out_dir = TRAIN_DIR / class_name
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(img_path, out_dir / "original.png")
    print(f"{img_path.name} -> dataset/train/{class_name}/original.png")

print("完成！")