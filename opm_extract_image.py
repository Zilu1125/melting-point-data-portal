import argparse
from pathlib import Path

DEFAULT_HEADER_SIZE = 336
DEFAULT_FRAME_SIZE = 28248
DEFAULT_FRAME_HEADER_SIZE = 24
DEFAULT_WIDTH = 196
DEFAULT_HEIGHT = 144


def save_pgm(output_path: Path, pixels: bytes, width: int, height: int) -> None:
    with open(output_path, "wb") as f:
        f.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        f.write(pixels)


def main():
    parser = argparse.ArgumentParser(
        description="Extract one image frame from an Optimelt .opm file using 0-based index."
    )
    parser.add_argument("opm_file", help="Path to the .opm file")
    parser.add_argument("index", type=int, help="0-based frame index")
    parser.add_argument("-o", "--output", help="Optional output file path")
    parser.add_argument("--raw", action="store_true", help="Write raw pixel bytes only")
    parser.add_argument("--png", action="store_true", help="Write PNG instead of PGM")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Image width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Image height")
    parser.add_argument("--header-size", type=int, default=DEFAULT_HEADER_SIZE, help="Global file header size")
    parser.add_argument("--frame-size", type=int, default=DEFAULT_FRAME_SIZE, help="Bytes per frame")
    parser.add_argument(
        "--frame-header-size",
        type=int,
        default=DEFAULT_FRAME_HEADER_SIZE,
        help="Bytes to skip at the start of each frame before pixel data",
    )

    args = parser.parse_args()

    opm_path = Path(args.opm_file)
    data = opm_path.read_bytes()

    if args.index < 0:
        raise ValueError("index must be >= 0")

    frame_start = args.header_size + args.index * args.frame_size
    frame_end = frame_start + args.frame_size

    if frame_end > len(data):
        raise IndexError("frame index out of range")

    frame_block = data[frame_start:frame_end]
    pixel_start = args.frame_header_size
    pixel_end = pixel_start + args.width * args.height
    pixels = frame_block[pixel_start:pixel_end]

    expected_pixels = args.width * args.height
    if len(pixels) != expected_pixels:
        raise ValueError(
            f"Pixel data length mismatch: got {len(pixels)}, expected {expected_pixels}. "
            f"Try adjusting --width, --height, or --frame-header-size."
        )

    # 默认输出到 frames 文件夹
    frames_dir = Path("frames")
    frames_dir.mkdir(exist_ok=True)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        if args.raw:
            ext = ".raw"
        elif args.png:
            ext = ".png"
        else:
            ext = ".pgm"
        output_path = frames_dir / f"frame_{args.index:04d}{ext}"

    if args.raw:
        output_path.write_bytes(pixels)
        print(f"Saved raw pixels to: {output_path}")
        return

    if args.png:
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("PNG output requires Pillow. Install it with: pip install pillow")

        img = Image.frombytes("L", (args.width, args.height), pixels)
        img.save(output_path)
        print(f"Saved PNG to: {output_path}")
        return

    save_pgm(output_path, pixels, args.width, args.height)
    print(f"Saved PGM to: {output_path}")


if __name__ == "__main__":
    main()