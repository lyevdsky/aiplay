from pathlib import Path
from PIL import Image
import random
import numpy as np
import cv2
import shutil

TRAIN_DIR = Path("dataset/train")


def augment_one_image(img, count_per_image):
    """对单张图做增强，返回增强后的图片列表"""
    h, w = np.array(img).shape[:2]
    results = []
    for _ in range(count_per_image):
        arr = np.array(img.copy())

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
                                  borderValue=(215, 215, 215))

        # ── 3. 轻微旋转 ±5° ─────────────────────────────
        angle = random.uniform(-5, 5)
        M_rot = cv2.getRotationMatrix2D((new_w / 2, new_h / 2), angle, 1.0)
        arr = cv2.warpAffine(arr, M_rot, (new_w, new_h),
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(215, 215, 215))

        # ── 4. 亮度扰动 ──────────────────────────────────
        factor = random.uniform(0.65, 1.15)
        arr = np.clip(arr.astype(float) * factor, 0, 255).astype(np.uint8)

        results.append(Image.fromarray(arr))
    return results


def augment_class_dir(class_dir, total_count=80):
    """处理单个类别文件夹：可能有1张original.png，也可能有多张真实素材"""
    images = list(class_dir.glob("*.png")) + list(class_dir.glob("*.jpg"))
    # 过滤掉之前生成的增强图，只保留原始素材
    source_images = [p for p in images if not p.stem.startswith("aug_")]

    if not source_images:
        return

    # 清理旧的增强图，避免重复累积
    for p in images:
        if p.stem.startswith("aug_"):
            p.unlink()

    n_sources = len(source_images)
    count_per_image = max(total_count // n_sources, 1)

    idx = 0
    for src_path in source_images:
        img = Image.open(src_path).convert("RGB")
        img = img.resize((126, 156), Image.LANCZOS)

        # 保存原图（resize后）
        img.save(class_dir / f"aug_{idx:03d}.png")
        idx += 1

        for aug_img in augment_one_image(img, count_per_image - 1):
            aug_img.save(class_dir / f"aug_{idx:03d}.png")
            idx += 1

    print(f"  {class_dir.name}: {n_sources}张原图 -> {idx}张增强图")


# ── 1. 先把 hard_examples 复制进 dataset/train ──────────────
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
        print(f"复制困难样本: {class_dir.name} ({len(images)}张)")

# ── 2. 对每个类别做增强 ──────────────────────────────────────
print("\n开始增强...")
for class_dir in sorted(TRAIN_DIR.iterdir()):
    if not class_dir.is_dir():
        continue
    augment_class_dir(class_dir, total_count=80)

print("\n增强完成！")
