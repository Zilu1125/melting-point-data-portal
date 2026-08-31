from pathlib import Path
from PIL import Image

# 输入主帧文件夹
input_dir = Path("frames")

# 输出文件夹
left_dir = Path("left_frames")
centre_dir = Path("centre_frames")
right_dir = Path("right_frames")

left_dir.mkdir(exist_ok=True)
centre_dir.mkdir(exist_ok=True)
right_dir.mkdir(exist_ok=True)

# 裁剪范围
# 你现在这版既然已经验证“准的”，就先用这一版
y1, y2 = 0, 144

left_x1, left_x2 = 0, 65
centre_x1, centre_x2 = 65, 130
right_x1, right_x2 = 130, 196

frame_files = sorted(input_dir.glob("frame_*.png"))

if not frame_files:
    print("No frame PNG files found in 'frames' folder.")
else:
    for img_path in frame_files:
        img = Image.open(img_path)

        left_img = img.crop((left_x1, y1, left_x2, y2))
        centre_img = img.crop((centre_x1, y1, centre_x2, y2))
        right_img = img.crop((right_x1, y1, right_x2, y2))

        left_img.save(left_dir / img_path.name)
        centre_img.save(centre_dir / img_path.name)
        right_img.save(right_dir / img_path.name)

        print(f"Processed {img_path.name}")