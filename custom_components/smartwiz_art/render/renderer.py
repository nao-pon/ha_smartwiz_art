from __future__ import annotations

import logging
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..core.models import HasImagePanelData, PanelData
from ..image.photo_pipeline import (
    PHOTO_PRESETS,
    choose_photo_preset,
    optimize_photo_for_epaper,
)
from ..translations.render import t
from .loader import load_template_registry

_LOGGER = logging.getLogger(__name__)

_TEMPLATE_REGISTRY = load_template_registry()


class SmartWizArtRenderer:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.font_dir = "/config/fonts"

    def _base_size(self) -> tuple[int, int]:
        # 横長レイアウトは 800x480 基準
        # 縦長レイアウトは 480x800 基準
        if self.height > self.width:
            return 480, 800
        return 800, 480

    def sx(self, value: float) -> int:
        base_w, _ = self._base_size()
        return round(value * (self.width / base_w))

    def sy(self, value: float) -> int:
        _, base_h = self._base_size()
        return round(value * (self.height / base_h))

    def sf(self, value: float) -> int:
        base_w, base_h = self._base_size()
        return max(1, round(value * min(self.width / base_w, self.height / base_h)))

    def render(self, template_type: str, data: PanelData) -> Image.Image:
        self._render_lang = getattr(data, "lang", "ja")

        entry = _TEMPLATE_REGISTRY.get(data.template)
        if entry is None:
            raise ValueError(f"Unsupported template: {data.template}")

        actual_type = entry.get("type")
        if actual_type != template_type:
            raise ValueError(
                f"Template type mismatch: requested={template_type}, actual={actual_type}"
            )

        render_func = entry["render"]
        img = render_func(self, data)

        if entry.get("orientation") == "portrait":
            img = img.rotate(90, expand=True)

        return img

    def _render_empty(self, data: PanelData):
        match data.theme:
            case "washi":
                img = self._create_washi_background()
            case _:
                img = self._create_washi_background()
        return img

    def _fit_image_center_crop(
        self, img: Image.Image, target_w: int, target_h: int
    ) -> Image.Image:
        src_w, src_h = img.size
        src_ratio = src_w / src_h
        target_ratio = target_w / target_h

        if abs(src_ratio - target_ratio) < 0.001:
            return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            img = img.crop((0, top, src_w, top + new_h))

        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def _draw_image_shadow(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        radius: int = 20,
    ) -> None:
        draw.rounded_rectangle(
            (x + 4, y + 4, x + w + 4, y + h + 4),
            radius=radius,
            fill=(210, 210, 210),
        )

    def _paste_rounded_image(
        self,
        base_img: Image.Image,
        src_img: Image.Image,
        x: int,
        y: int,
        w: int,
        h: int,
        radius: int = 20,
        photo_preset: str = "natural",
    ) -> None:
        fitted = self._fit_image_center_crop(src_img, w, h).convert("RGB")
        fitted = optimize_photo_for_epaper(
            fitted,
            adjust=PHOTO_PRESETS.get(photo_preset, PHOTO_PRESETS["natural"]),
        ).convert("RGBA")

        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)

        rounded = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rounded.paste(fitted, (0, 0))
        rounded.putalpha(mask)

        base_img.paste(rounded, (x, y), rounded)

    def _draw_side_image(
        self,
        base_img: Image.Image,
        data: HasImagePanelData,
    ) -> None:
        image_path = data.image_path
        if not image_path:
            return

        path = Path(image_path)
        if not path.exists():
            return

        target_x = self.sx(300)
        target_y = self.sy(12)
        target_w = self.width - target_x - self.sx(12)
        target_h = self.height - self.sy(24)

        try:
            with Image.open(path) as src:
                src_rgb = src.convert("RGB")
                src_rgba = src_rgb.convert("RGBA")

                if data.photo_preset == "auto":
                    (
                        data.resolved_photo_preset,
                        data.photo_avg_luma,
                        data.photo_contrast,
                    ) = choose_photo_preset(src_rgb)
                else:
                    data.resolved_photo_preset = data.photo_preset or "natural"

                draw = ImageDraw.Draw(base_img)

                self._draw_image_shadow(
                    draw,
                    target_x,
                    target_y,
                    target_w,
                    target_h,
                    radius=self.sf(20),
                )

                self._paste_rounded_image(
                    base_img,
                    src_rgba,
                    target_x,
                    target_y,
                    target_w,
                    target_h,
                    radius=self.sf(20),
                    photo_preset=data.resolved_photo_preset,
                )
        except Exception as err:
            _LOGGER.exception("Failed to draw side image: %s", err)
            return

    def _create_washi_background(self) -> Image.Image:
        """
        外周用の、少し強めの和紙。
        以前より粒感とムラを一段上げる。
        """
        base_color = (242, 239, 230)
        img = Image.new("RGB", (self.width, self.height), base_color)
        px = img.load()

        for y in range(self.height):
            for x in range(self.width):
                noise = random.randint(-10, 10)

                # 繊維や少し濃い粒のような点
                if random.random() < 0.020:
                    noise -= random.randint(5, 14)

                # たまに少し明るい粒
                if random.random() < 0.008:
                    noise += random.randint(2, 7)

                r, g, b = base_color
                px[x, y] = (
                    max(0, min(255, r + noise)),
                    max(0, min(255, g + noise)),
                    max(0, min(255, b + noise)),
                )

        return img.filter(ImageFilter.GaussianBlur(0.45))

    def _draw_content_panels(self, draw: ImageDraw.ImageDraw) -> None:
        """
        外周: 強めの和紙
        中間: 静かな余白帯
        内側: 情報面
        の3層構造。
        """
        outer_margin = self.sx(20)
        gap_margin = self.sx(28)
        inner_margin = self.sx(36)
        top = self.sy(16)
        bottom = self.height - self.sy(16)

        # 1) 外周の内側境界
        # 素材感は背景側に任せて、線は少し弱めにする
        draw.rounded_rectangle(
            (outer_margin, top, self.width - outer_margin, bottom),
            radius=self.sf(18),
            outline=(95, 95, 95),
            width=max(1, self.sf(1)),
        )

        # 2) 呼吸用の静かな帯
        draw.rounded_rectangle(
            (
                gap_margin,
                top + self.sy(6),
                self.width - gap_margin,
                bottom - self.sy(6),
            ),
            radius=self.sf(18),
            fill=(246, 243, 236),
        )

        # 3) 情報面
        draw.rounded_rectangle(
            (
                inner_margin,
                top + self.sy(14),
                self.width - inner_margin,
                bottom - self.sy(14),
            ),
            radius=self.sf(16),
            fill=(249, 247, 241),
            outline=(75, 75, 75),
            width=max(1, self.sf(1)),
        )

    def _draw_season_band(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int
    ) -> None:
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=12,
            fill=(232, 228, 216),
            outline=(100, 100, 100),
            width=1,
        )
        draw.line((x + 18, y + 18, x + w - 18, y + 18), fill=(130, 130, 130), width=1)
        draw.line(
            (x + 18, y + h - 18, x + w - 18, y + h - 18), fill=(130, 130, 130), width=1
        )

    def _draw_message_box(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int
    ) -> None:
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=16,
            fill=(247, 245, 238),
            outline=(65, 65, 65),
            width=1,
        )

    def _draw_rule(self, draw: ImageDraw.ImageDraw, x: int, y: int, w: int) -> None:
        draw.line((x, y, x + w, y), fill=(40, 40, 40), width=2)

    def _draw_bullet_line(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font
    ) -> None:
        bullet_r = 5
        cy = y + 18
        draw.ellipse((x, cy - bullet_r, x + bullet_r * 2, cy + bullet_r), fill="black")
        draw.text((x + 22, y), text, font=font, fill="black")

    def _draw_text_in_box(
        self,
        draw,
        text: str,
        box: tuple[int, int, int, int],
        font,
        fill="black",
        line_spacing=6,
        align="left",
        valign="top",
        wrap=True,
        ellipsis=False,
    ):
        def _fit_text_with_ellipsis(draw, text: str, font, max_width: int) -> str:
            ellipsis_text = "..."
            ellipsis_bbox = draw.textbbox((0, 0), ellipsis_text, font=font)
            ellipsis_w = ellipsis_bbox[2] - ellipsis_bbox[0]

            if ellipsis_w > max_width:
                return ""

            current = ""
            for ch in text:
                trial = current + ch
                bbox = draw.textbbox((0, 0), trial, font=font)
                trial_w = bbox[2] - bbox[0]

                if trial_w + ellipsis_w <= max_width:
                    current = trial
                else:
                    break

            return current + ellipsis_text

        x1, y1, x2, y2 = box
        box_w = x2 - x1
        box_h = y2 - y1

        if align not in ("left", "center", "right"):
            align = "left"
        if valign not in ("top", "center", "bottom"):
            valign = "top"

        if not text:
            return

        lines = self._wrap_text(draw, text, font, box_w) if wrap else [text]
        if not lines:
            return

        line_metrics = []
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            line_metrics.append((line, line_w, line_h))
            total_h += line_h

        total_h += line_spacing * (len(line_metrics) - 1 if line_metrics else 0)

        if valign == "top":
            cursor_y = y1
        elif valign == "bottom":
            cursor_y = y2 - total_h
        else:
            cursor_y = y1 + (box_h - total_h) // 2

        for i, (line, line_w, line_h) in enumerate(line_metrics):
            # はみ出す場合
            if cursor_y + line_h > y2:
                if ellipsis and i > 0:
                    prev_line, _, prev_h = line_metrics[i - 1]
                    fitted = _fit_text_with_ellipsis(draw, prev_line, font, box_w)

                    prev_y = cursor_y - (line_spacing + prev_h)

                    # 再描画
                    if align == "center":
                        bbox = draw.textbbox((0, 0), fitted, font=font)
                        w = bbox[2] - bbox[0]
                        cursor_x = x1 + (box_w - w) // 2
                    elif align == "right":
                        bbox = draw.textbbox((0, 0), fitted, font=font)
                        w = bbox[2] - bbox[0]
                        cursor_x = x2 - w
                    else:
                        cursor_x = x1

                    draw.text((cursor_x, prev_y), fitted, font=font, fill=fill)

                break

            # 通常描画
            if align == "center":
                cursor_x = x1 + (box_w - line_w) // 2
            elif align == "right":
                cursor_x = x2 - line_w
            else:
                cursor_x = x1

            draw.text((cursor_x, cursor_y), line, font=font, fill=fill)
            cursor_y += line_h + line_spacing

    def _draw_centered_text(
        self,
        draw,
        text: str,
        box: tuple[int, int, int, int],
        font,
        fill="black",
        line_spacing=6,
        valign="center",
    ):
        self._draw_text_in_box(
            draw,
            text,
            box,
            font,
            fill=fill,
            line_spacing=line_spacing,
            align="center",
            valign=valign,
            wrap=True,
        )

    def _draw_wrapped_text(
        self,
        draw,
        text,
        box,
        font,
        fill="black",
        line_spacing=6,
    ):
        self._draw_text_in_box(
            draw,
            text,
            box,
            font,
            fill=fill,
            line_spacing=line_spacing,
            align="left",
            valign="top",
            wrap=True,
        )

    def _wrap_text(self, draw, text, font, max_width):
        lines = []
        current = ""
        for ch in text:
            trial = current + ch
            bbox = draw.textbbox((0, 0), trial, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
        return lines

    def _load_font(self, size: int, bold: bool = False):
        candidates = [
            f"{self.font_dir}/NotoSansJP-Bold.ttf"
            if bold
            else f"{self.font_dir}/NotoSansJP-Medium.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _load_font_pair(self, size: int, bold: bool = False):
        text_candidates = [
            f"{self.font_dir}/NotoSansJP-Bold.ttf"
            if bold
            else f"{self.font_dir}/NotoSansJP-Medium.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        emoji_candidates = [
            f"{self.font_dir}/NotoEmoji-Medium.ttf",
        ]

        text_font = None
        emoji_font = None

        for path in text_candidates:
            try:
                text_font = ImageFont.truetype(path, size=int(size * 0.5))
                break
            except Exception:
                pass

        for path in emoji_candidates:
            try:
                emoji_font = ImageFont.truetype(path, size=size)
                break
            except Exception:
                pass

        if text_font is None:
            text_font = ImageFont.load_default()

        if emoji_font is None:
            emoji_font = text_font

        return text_font, emoji_font

    def _weather_icon(self, condition: str) -> str:
        if not condition:
            return "◯"

        key = str(condition).strip().lower()

        mapping = {
            "sunny": "☀",
            "clear-night": "🌙",
            "partlycloudy": "⛅",
            "cloudy": "☁",
            "fog": "〰",
            "rainy": "☔",
            "pouring": "☔",
            "lightning": "⚡",
            "lightning-rainy": "⛈",
            "snowy": "☃",
            "snowy-rainy": "🌨",
            "hail": "❄",
            "windy": "🌀",
            "windy-variant": "☁",
            "exceptional": "❕",
        }
        return mapping.get(key, "◯")

    def _weather_label(self, condition: str) -> str:
        if not condition:
            return t(getattr(self, "_render_lang", "ja"), "unknown")

        key = str(condition).strip().lower()
        mapping = {
            "sunny": t(getattr(self, "_render_lang", "ja"), "weather.sunny"),
            "clear-night": t(
                getattr(self, "_render_lang", "ja"), "weather.clear-night"
            ),
            "partlycloudy": t(
                getattr(self, "_render_lang", "ja"), "weather.partlycloudy"
            ),
            "cloudy": t(getattr(self, "_render_lang", "ja"), "weather.cloudy"),
            "fog": t(getattr(self, "_render_lang", "ja"), "weather.fog"),
            "rainy": t(getattr(self, "_render_lang", "ja"), "weather.rainy"),
            "pouring": t(getattr(self, "_render_lang", "ja"), "weather.pouring"),
            "lightning": t(getattr(self, "_render_lang", "ja"), "weather.lightning"),
            "lightning-rainy": t(
                getattr(self, "_render_lang", "ja"), "weather.lightning-rainy"
            ),
            "snowy": t(getattr(self, "_render_lang", "ja"), "weather.snowy"),
            "snowy-rainy": t(
                getattr(self, "_render_lang", "ja"), "weather.snowy-rainy"
            ),
            "hail": t(getattr(self, "_render_lang", "ja"), "weather.hail"),
            "windy": t(getattr(self, "_render_lang", "ja"), "weather.windy"),
            "windy-variant": t(
                getattr(self, "_render_lang", "ja"), "weather.windy-variant"
            ),
            "exceptional": t(
                getattr(self, "_render_lang", "ja"), "weather.exceptional"
            ),
        }
        return mapping.get(key, condition)
