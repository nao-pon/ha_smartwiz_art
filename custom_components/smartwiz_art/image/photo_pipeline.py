from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps

from .photo_lab import apply_gamma, auto_tone_curve_lab, calc_avg_luma, calc_contrast


@dataclass(frozen=True)
class PhotoAdjust:
    auto_tone_black_ratio: float = 0.02
    auto_tone_white_ratio: float = 0.98
    lightness_lift: float = 1.1
    gamma: float = 0.95
    autocontrast_cutoff: float = 0.3
    saturation: float = 1.03
    contrast: float = 1.00
    sharpness: float = 1.00
    scurve_strength: float = 0.08
    auto_tone: bool = True


PHOTO_PRESETS: dict[str, PhotoAdjust] = {
    "natural": PhotoAdjust(
        auto_tone_black_ratio=0.02,
        auto_tone_white_ratio=0.98,
        lightness_lift=1.1,
        gamma=0.7,
        autocontrast_cutoff=0.3,
        saturation=1.03,
        contrast=1.00,
        sharpness=1.00,
        scurve_strength=0.08,
        auto_tone=True,
    ),
    "vivid": PhotoAdjust(
        auto_tone_black_ratio=0.02,
        auto_tone_white_ratio=0.98,
        lightness_lift=1.05,
        gamma=0.6,
        autocontrast_cutoff=0.35,
        saturation=1.06,
        contrast=1.00,
        sharpness=1.00,
        scurve_strength=0.12,
        auto_tone=True,
    ),
    "soft": PhotoAdjust(
        auto_tone_black_ratio=0.015,
        auto_tone_white_ratio=0.985,
        lightness_lift=1.15,
        gamma=0.9,
        autocontrast_cutoff=0.2,
        saturation=1.01,
        contrast=1.00,
        sharpness=1.00,
        scurve_strength=0.04,
        auto_tone=True,
    ),
}


def optimize_photo_for_epaper(
    img: Image.Image,
    adjust: PhotoAdjust | None = None,
) -> Image.Image:
    """
    6色 e-ink 向け写真補正。
    役割は「最終パレット量子化の前の下ごしらえ」に留める。
    強くやりすぎるとパレット側と二重に効くので、少し控えめにする。
    """
    adjust = adjust or PHOTO_PRESETS["natural"]

    img = img.convert("RGB")

    if adjust.auto_tone:
        img = auto_tone_curve_lab(
            img,
            black_ratio=adjust.auto_tone_black_ratio,
            white_ratio=adjust.auto_tone_white_ratio,
            lift=adjust.lightness_lift,
            scurve_strength=adjust.scurve_strength,
        )
    else:
        img = ImageOps.autocontrast(img, cutoff=adjust.autocontrast_cutoff)

    if adjust.gamma != 1.0:
        img = apply_gamma(img, adjust.gamma)

    if abs(adjust.saturation - 1.0) > 1e-6:
        img = ImageEnhance.Color(img).enhance(adjust.saturation)

    if abs(adjust.contrast - 1.0) > 1e-6:
        img = ImageEnhance.Contrast(img).enhance(adjust.contrast)

    if abs(adjust.sharpness - 1.0) > 1e-6:
        img = ImageEnhance.Sharpness(img).enhance(adjust.sharpness)

    return img


def choose_photo_preset(img) -> tuple[str, float, float]:
    luma = calc_avg_luma(img)
    contrast = calc_contrast(img)

    if luma < 90:
        return "soft", luma, contrast
    elif contrast < 30:
        return "vivid", luma, contrast  # 眠い画像
    else:
        return "natural", luma, contrast
