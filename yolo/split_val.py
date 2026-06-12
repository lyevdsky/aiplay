# split_val.py
import shutil, random
from pathlib import Path

train_root = Path("dataset/train")
val_root = Path("dataset/val")

for class_dir in train_root.iterdir():
    if not class_dir.is_dir():
        continue
    images = list(class_dir.glob("*.png"))
    val_samples = random.sample(images, k=min(4, len(images)))  # 每类抽4张做val
    
    val_class_dir = val_root / class_dir.name
    val_class_dir.mkdir(parents=True, exist_ok=True)
    
    for img_path in val_samples:
        shutil.copy(img_path, val_class_dir / img_path.name)

print("val集生成完成！")