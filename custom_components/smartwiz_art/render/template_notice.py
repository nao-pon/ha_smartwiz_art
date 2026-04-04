from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from ..translations.render import t

if TYPE_CHECKING:
    from ..core.models import NoticePanelData
    from .renderer import SmartWizArtRenderer


TEMPLATES = {
    "notice": {
        "type": "notice",
        "orientation": "portrait",
    },
}


def render(
    renderer: "SmartWizArtRenderer",
    data: "NoticePanelData",
) -> Image.Image:
    match data.theme:
        case "washi":
            img = renderer._create_washi_background()
        case _:
            img = renderer._create_washi_background()

    draw = ImageDraw.Draw(img)
    renderer._draw_content_panels(draw)

    font_title = renderer._load_font(renderer.sf(28), bold=True)
    font_date = renderer._load_font(renderer.sf(18), bold=False)
    font_body = renderer._load_font(renderer.sf(26), bold=False)
    font_small = renderer._load_font(renderer.sf(15), bold=False)

    margin_x = renderer.sx(48)
    content_w = renderer.width - margin_x * 2

    title_text = data.title.strip() if data.title else t(data.lang, "notice")

    title_y = renderer.sy(40)
    renderer._draw_centered_text(
        draw,
        title_text,
        (margin_x, title_y, margin_x + content_w, title_y + renderer.sy(34)),
        font_title,
        valign="center",
    )

    date_y = title_y + renderer.sy(42)
    renderer._draw_centered_text(
        draw,
        f"{data.date} {data.weekday}".strip(),
        (margin_x, date_y, margin_x + content_w, date_y + renderer.sy(24)),
        font_date,
        valign="center",
    )

    renderer._draw_rule(draw, margin_x, date_y + renderer.sy(34), content_w)

    body_top = date_y + renderer.sy(54)
    body_bottom = renderer.height - renderer.sy(90)

    body_text = data.body.strip() if data.body else t(data.lang, "default_message")
    renderer._draw_text_in_box(
        draw,
        body_text,
        (
            margin_x + renderer.sx(8),
            body_top,
            renderer.width - margin_x - renderer.sx(8),
            body_bottom,
        ),
        font_body,
        line_spacing=renderer.sy(8),
        align="center",
        valign="center",
        wrap=True,
    )

    updated_y = renderer.height - renderer.sy(54)
    renderer._draw_centered_text(
        draw,
        f"{data.updated} {t(data.lang, 'updated')}".strip(),
        (margin_x, updated_y, margin_x + content_w, updated_y + renderer.sy(20)),
        font_small,
        valign="center",
    )

    return img
