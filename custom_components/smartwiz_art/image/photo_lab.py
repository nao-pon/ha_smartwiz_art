from __future__ import annotations

import math

from PIL import Image, ImageStat

# D65 white point
_XN = 0.95047
_YN = 1.00000
_ZN = 1.08883


def _srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def _f_xyz_to_lab(t: float) -> float:
    delta = 6 / 29
    if t > delta**3:
        return t ** (1 / 3)
    return t / (3 * delta**2) + 4 / 29


def _f_lab_to_xyz(t: float) -> float:
    delta = 6 / 29
    if t > delta:
        return t**3
    return 3 * delta**2 * (t - 4 / 29)


def rgb_to_lab_pixel(r: int, g: int, b: int) -> tuple[float, float, float]:
    rs = _srgb_to_linear(r / 255.0)
    gs = _srgb_to_linear(g / 255.0)
    bs = _srgb_to_linear(b / 255.0)

    # linear RGB -> XYZ
    x = rs * 0.4124564 + gs * 0.3575761 + bs * 0.1804375
    y = rs * 0.2126729 + gs * 0.7151522 + bs * 0.0721750
    z = rs * 0.0193339 + gs * 0.1191920 + bs * 0.9503041

    fx = _f_xyz_to_lab(x / _XN)
    fy = _f_xyz_to_lab(y / _YN)
    fz = _f_xyz_to_lab(z / _ZN)

    l = 116 * fy - 16
    a = 500 * (fx - fy)
    bb = 200 * (fy - fz)
    return l, a, bb


def lab_to_rgb_pixel(l: float, a: float, b: float) -> tuple[int, int, int]:
    fy = (l + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    x = _XN * _f_lab_to_xyz(fx)
    y = _YN * _f_lab_to_xyz(fy)
    z = _ZN * _f_lab_to_xyz(fz)

    # XYZ -> linear RGB
    rl = x * 3.2404542 + y * -1.5371385 + z * -0.4985314
    gl = x * -0.9692660 + y * 1.8760108 + z * 0.0415560
    bl = x * 0.0556434 + y * -0.2040259 + z * 1.0572252

    rl = max(0.0, min(1.0, rl))
    gl = max(0.0, min(1.0, gl))
    bl = max(0.0, min(1.0, bl))

    r = round(max(0.0, min(1.0, _linear_to_srgb(rl))) * 255)
    g = round(max(0.0, min(1.0, _linear_to_srgb(gl))) * 255)
    b = round(max(0.0, min(1.0, _linear_to_srgb(bl))) * 255)
    return r, g, b


def _build_l_curve_lut(strength: float = 0.22) -> list[float]:
    """
    L* 0..100 用の軽いSカーブLUT
    """
    strength = max(0.0, min(1.0, strength))
    k = 2.0 + strength * 6.0

    lut: list[float] = []
    for i in range(101):
        x = i / 100.0
        y = 0.5 + 0.5 * math.tanh(k * (x - 0.5)) / math.tanh(k * 0.5)
        lut.append(y * 100.0)
    return lut


def _hist_percentile(hist: list[int], ratio: float) -> int:
    total = sum(hist)
    threshold = total * ratio
    acc = 0
    for i, count in enumerate(hist):
        acc += count
        if acc >= threshold:
            return i
    return 255


def auto_tone_curve_lab(
    img: Image.Image,
    black_ratio: float = 0.01,
    white_ratio: float = 0.99,
    lift: float = 0.0,
    scurve_strength: float = 0.22,
) -> Image.Image:
    """
    Pillowのみで行う LAB ベースの自動トーン補正。
    - 画像全体のL*ヒストグラムから black/white を決定
    - L*のみ線形補正
    - その後 L* にSカーブ適用
    - a,b はそのまま維持

    black_ratio=0.01, white_ratio=0.99 は
    下位1%, 上位1%を外れ値として無視するイメージ。
    """
    img = img.convert("RGB")
    src = img.load()
    w, h = img.size

    l_hist = [0] * 256

    # L* ヒストグラム作成
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            l, _, _ = rgb_to_lab_pixel(r, g, b)
            idx = max(0, min(255, round(l * 255 / 100)))
            l_hist[idx] += 1

    black_idx = _hist_percentile(l_hist, black_ratio)
    white_idx = _hist_percentile(l_hist, white_ratio)

    if white_idx <= black_idx:
        white_idx = min(255, black_idx + 1)

    l_lut = _build_l_curve_lut(scurve_strength)

    out = Image.new("RGB", (w, h))
    out_px = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            l, a, bb = rgb_to_lab_pixel(r, g, b)

            # 0..100 -> 0..255 相当に一旦マップしてレベル補正
            l255 = l * 255 / 100.0
            l255 = (l255 - black_idx) * 255.0 / (white_idx - black_idx)
            l255 = max(0.0, min(255.0, l255))

            # 戻す
            l = l255 * 100.0 / 255.0

            # 全体持ち上げ
            l = max(0.0, min(100.0, l + lift))

            # Sカーブ
            lut_idx = max(0, min(100, round(l)))
            l = l_lut[lut_idx]

            out_px[x, y] = lab_to_rgb_pixel(l, a, bb)

    return out


def apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    if gamma == 1.0:
        return img

    inv_gamma = 1.0 / gamma

    lut = [int((i / 255.0) ** inv_gamma * 255.0 + 0.5) for i in range(256)]

    return img.point(lut * 3)


def calc_avg_luma(img):
    # グレースケールに変換
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    return stat.mean[0]  # 0〜255


def calc_contrast(img):
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    return stat.stddev[0]
