from pathlib import Path
from PIL import Image
import shutil
import random
import numpy as np
import cv2

TRAIN_DIR = Path("dataset/train")

def augment_tile(src_path, out_dir, count=80):
    img = Image.open(src_path).convert("RGB")
    img = img.resize((126, 156), Image.LANCZOS)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 保存原图
    img.save(out_dir / "aug_000.png")

    for i in range(1, count):
        arr = np.array(img.copy())
        h, w = arr.shape[:2]

        # ── 1. 横向 + 纵向压缩 ──────────────────────────
        scale_x = random.uniform(0.30, 1.0)
        scale_y = random.uniform(0.58, 1.0)
        new_w = max(int(w * scale_x), 10)
        new_h = max(int(h * scale_y), 10)
        arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # ── 2. 平行四边形剪切变换 ────────────────────────
        max_shear = int(new_h * 0.08)
        shear_px = random.randint(-max_shear, max_shear)
        src_pts = np.float32([[0, 0], [new_w, 0], [new_w, new_h], [0, new_h]])
        dst_pts = np.float32([
            [0,      0],
            [new_w,  shear_px],
            [new_w,  new_h + shear_px],
            [0,      new_h]
        ])
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        arr = cv2.warpPerspective(arr, M, (new_w, new_h),
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(255, 255, 255))

        # ── 3. 轻微旋转 ±5° ─────────────────────────────
        angle = random.uniform(-5, 5)
        M_rot = cv2.getRotationMatrix2D((new_w / 2, new_h / 2), angle, 1.0)
        arr = cv2.warpAffine(arr, M_rot, (new_w, new_h),
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(255, 255, 255))

        # ── 4. 亮度扰动 ──────────────────────────────────
        factor = random.uniform(0.65, 1.15)
        arr = np.clip(arr.astype(float) * factor, 0, 255).astype(np.uint8)

        # ── 5. 直接保存压缩后的真实尺寸 ──────────────────
        aug = Image.fromarray(arr)
        aug.save(out_dir / f"aug_{i:03d}.png")


# 遍历所有类别
src_root = Path("dataset/train")
for class_dir in src_root.iterdir():
    if not class_dir.is_dir():
        continue
    images = list(class_dir.glob("original.png"))
    if not images:
        continue
    print(f"增强类别: {class_dir.name}")
    augment_tile(images[0], class_dir, count=80)

print("增强完成！")

# 复制 hard_examples 到 dataset/train
hard_root = Path("./hard_examples")
if hard_root.exists():
    for class_dir in hard_root.iterdir():
        if not class_dir.is_dir():
            continue
        images = list(class_dir.glob("*.png")) + list(class_dir.glob("*.jpg"))
        if not images:
            continue
        out_dir = TRAIN_DIR / class_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for img_path in images:
            dst = out_dir / f"hard_{img_path.name}"
            shutil.copy(img_path, dst)
            print(f"复制困难样本: {img_path} -> {dst}")