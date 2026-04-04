from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image

from .photo_pipeline import (
    PHOTO_PRESETS,
    choose_photo_preset,
    optimize_photo_for_epaper,
)

WIDTH = 800
HEIGHT = 480


def build_palette_image(palette_path: Path | None = None) -> Image.Image:
    if palette_path and palette_path.exists():
        pal = Image.open(palette_path)
        if pal.mode != "P":
            pal = pal.convert("P", palette=Image.Palette.ADAPTIVE, colors=6)
        return pal

    palette_colors = [
        (0, 0, 0),  # black
        (255, 255, 255),  # white
        (255, 255, 0),  # yellow
        (255, 0, 0),  # red
        (0, 0, 255),  # blue
        (0, 255, 0),  # green
    ]

    pal = Image.new("P", (1, 1))
    flat: list[int] = []
    for rgb in palette_colors:
        flat.extend(rgb)

    flat.extend([0] * (768 - len(flat)))
    pal.putpalette(flat)
    return pal


def rgba_to_panel_color(r: int, g: int, b: int, a: int) -> int:
    r = (r * a) // 255
    g = (g * a) // 255
    b = (b * a) // 255

    rgb = (r << 16) | (g << 8) | b

    if rgb == 0x000000:
        return 0  # BLACK
    if rgb == 0xFFFF00:
        return 2  # YELLOW
    if rgb == 0xFF0000:
        return 3  # RED
    if rgb == 0x0000FF:
        return 5  # BLUE
    if rgb == 0x00FF00:
        return 6  # GREEN
    return 1  # WHITE


def fit_image_crop(
    img: Image.Image, target_width: int, target_height: int
) -> Image.Image:
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_width / target_height

    if abs(src_ratio - target_ratio) < 0.001:
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    return img.resize((target_width, target_height), Image.Resampling.LANCZOS)


def fit_image_fit(
    img: Image.Image,
    target_width: int,
    target_height: int,
    background: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> Image.Image:
    canvas = Image.new("RGBA", (target_width, target_height), background)
    fitted = img.copy()
    fitted.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

    x = (target_width - fitted.width) // 2
    y = (target_height - fitted.height) // 2

    if fitted.mode == "RGBA":
        canvas.paste(fitted, (x, y), fitted)
    else:
        canvas.paste(fitted, (x, y))
    return canvas


def fit_image_stretch(
    img: Image.Image, target_width: int, target_height: int
) -> Image.Image:
    return img.resize((target_width, target_height), Image.Resampling.LANCZOS)


def apply_image_fit(
    img: Image.Image,
    target_width: int,
    target_height: int,
    image_fit: str = "crop",
) -> Image.Image:
    mode = str(image_fit or "crop").strip().lower()

    if mode == "fit":
        return fit_image_fit(img, target_width, target_height)
    if mode == "stretch":
        return fit_image_stretch(img, target_width, target_height)

    return fit_image_crop(img, target_width, target_height)


def apply_photo_preset(img: Image.Image, photo_preset: str = "auto") -> Image.Image:
    preset = str(photo_preset or "auto").strip().lower()
    rgb = img.convert("RGB")

    if preset == "auto":
        preset, _, _ = choose_photo_preset(rgb)

    adjust = PHOTO_PRESETS.get(preset, PHOTO_PRESETS["natural"])
    tuned = optimize_photo_for_epaper(rgb, adjust=adjust)

    if img.mode == "RGBA":
        out = tuned.convert("RGBA")
        out.putalpha(img.getchannel("A"))
        return out

    return tuned


def quantize_to_panel_palette(
    input_image: Path,
    palette_path: Path | None = None,
    target_width: int = WIDTH,
    target_height: int = HEIGHT,
    auto_rotate_portrait: bool = True,
    dither: bool = True,
    image_fit: str | None = None,
    photo_preset: str | None = None,
) -> Image.Image:
    img = Image.open(input_image).convert("RGBA")

    # 縦長テンプレは反時計回りに90度回転
    if auto_rotate_portrait and img.height > img.width:
        img = img.rotate(90, expand=True)

    if image_fit:
        img = apply_image_fit(
            img,
            target_width=target_width,
            target_height=target_height,
            image_fit=image_fit,
        )

    if photo_preset:
        img = apply_photo_preset(img, photo_preset=photo_preset)

    palette_img = build_palette_image(palette_path)

    rgb_img = img.convert("RGB")
    quantized = rgb_img.quantize(
        palette=palette_img,
        dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE,
    )

    rgba_quantized = quantized.convert("RGBA")
    alpha = img.getchannel("A")
    rgba_quantized.putalpha(alpha)

    return rgba_quantized


def pack_s6(img: Image.Image) -> bytes:
    img = img.convert("RGBA")
    width, height = img.size
    raw = img.tobytes("raw", "BGRA")

    cfb = bytearray((width * height) // 2)
    index = 0

    for i in range(0, len(raw), 4):
        b = raw[i + 0]
        g = raw[i + 1]
        r = raw[i + 2]
        a = raw[i + 3]

        color = rgba_to_panel_color(r, g, b, a)

        if index & 1:
            cfb[index >> 1] |= color
        else:
            cfb[index >> 1] |= color << 4

        index += 1
        if index >= width * height:
            break

    return bytes(cfb)


#     return output_path
def convert_image_file(
    input_image: str | Path,
    output_image: str | Path,
    target_width: int = WIDTH,
    target_height: int = HEIGHT,
    auto_rotate_portrait: bool = True,
    convert_options: dict | None = None,
) -> Path:
    input_path = Path(input_image)
    output_path = Path(output_image)
    convert_options = convert_options or {}
    palette_path = convert_options.get("palette_path")

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    palette = (
        Path(palette_path) if palette_path else Path(__file__).with_name("palette.png")
    )
    dither = convert_options.get("dither", True)
    image_fit = convert_options.get("image_fit")
    photo_preset = convert_options.get("photo_preset")

    quantized = quantize_to_panel_palette(
        input_path,
        palette,
        target_width=target_width,
        target_height=target_height,
        auto_rotate_portrait=auto_rotate_portrait,
        dither=dither,
        image_fit=image_fit,
        photo_preset=photo_preset,
    )
    payload = pack_s6(quantized)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    return output_path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 convert_image.py <input_image> <output_image.s6>")
        return 1

    try:
        convert_image_file(sys.argv[1], sys.argv[2])
        print(f"Converted: {sys.argv[1]} -> {sys.argv[2]}")
        return 0
    except Exception as e:
        print(f"Convert failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
