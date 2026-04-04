from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from ..translations.render import t

if TYPE_CHECKING:
    from ..core.models import TodayPanelData
    from .renderer import SmartWizArtRenderer

TEMPLATES = {
    "today": {
        "type": "today",
        "orientation": "portrait",
    },
    "today_with_image": {
        "type": "today",
        "orientation": "landscape",
    },
}


def render(renderer: "SmartWizArtRenderer", data: "TodayPanelData") -> Image.Image:
    match data.theme:
        case "washi":
            img = renderer._create_washi_background()
        case _:
            img = renderer._create_washi_background()

    # if data.image_path:
    if data.template == "today_with_image":
        return _render_today_with_image_landscape(renderer, data, img)
    else:
        return _render_today_standard(renderer, data, img)


def _render_today_standard(
    renderer: "SmartWizArtRenderer", data: "TodayPanelData", img: Image.Image
) -> Image.Image:
    draw = ImageDraw.Draw(img)

    renderer._draw_content_panels(draw)

    font_date = renderer._load_font(renderer.sf(32), bold=True)
    font_weekday = renderer._load_font(renderer.sf(24), bold=False)
    font_weather, font_weather_emoji = renderer._load_font_pair(
        renderer.sf(48), bold=True
    )
    font_temp = renderer._load_font(renderer.sf(32), bold=True)
    font_section = renderer._load_font(renderer.sf(18), bold=True)
    font_body = renderer._load_font(renderer.sf(18), bold=False)
    font_small = renderer._load_font(renderer.sf(15), bold=False)
    font_message = renderer._load_font(renderer.sf(20), bold=False)
    margin_x = renderer.sx(48)
    content_w = renderer.width - margin_x * 2

    date_y = renderer.sy(42)
    draw.text((margin_x, date_y), data.date, font=font_date, fill="black")
    date_bbox = draw.textbbox((margin_x, date_y), data.date, font=font_date)

    weekday_x = date_bbox[2] + renderer.sx(10)
    draw.text(
        (weekday_x, date_y + renderer.sy(16)),
        data.weekday,
        font=font_weekday,
        fill="black",
    )

    band_y = date_y + renderer.sy(58)
    renderer._draw_season_band(draw, margin_x, band_y, content_w, renderer.sy(34))

    weather_y = band_y + renderer.sy(46)
    icon = renderer._weather_icon(data.weather)
    label = renderer._weather_label(data.weather)
    draw.text((margin_x, weather_y), icon, font=font_weather_emoji, fill="black")
    draw.text(
        (margin_x + renderer.sx(60), weather_y + renderer.sy(4)),
        label,
        font=font_weather,
        fill="black",
    )

    temp_text = data.temperature
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_temp)
    temp_w = temp_bbox[2] - temp_bbox[0]
    draw.text(
        (renderer.width - margin_x - temp_w, weather_y - renderer.sy(2)),
        temp_text,
        font=font_temp,
        fill="black",
    )

    if data.rain:
        draw.text(
            (margin_x, weather_y + renderer.sy(54)),
            f"{t(data.lang, 'rain')} {data.rain}",
            font=font_small,
            fill="black",
        )

    renderer._draw_rule(draw, margin_x, weather_y + renderer.sy(90), content_w)

    section_y = weather_y + renderer.sy(110)
    draw.text(
        (margin_x, section_y),
        t(data.lang, "today_schedule"),
        font=font_section,
        fill="black",
    )

    item_y = section_y + renderer.sy(28)
    max_schedule = 3
    for item in list(data.schedule)[:max_schedule]:
        renderer._draw_bullet_line(
            draw, margin_x + renderer.sx(2), item_y, item, font_body
        )
        item_y += renderer.sy(26)

    if not data.schedule:
        draw.text(
            (margin_x + renderer.sx(2), item_y),
            t(data.lang, "no_schedule"),
            font=font_body,
            fill="black",
        )

    renderer._draw_rule(draw, margin_x, item_y + renderer.sy(46), content_w)

    status_y = item_y + renderer.sy(56)
    draw.text(
        (margin_x, status_y), t(data.lang, "home"), font=font_section, fill="black"
    )

    status_text = (
        "   ".join(data.home_status[:4])
        if data.home_status
        else t(data.lang, "no_status")
    )
    renderer._draw_wrapped_text(
        draw,
        status_text,
        (
            margin_x,
            status_y + renderer.sy(24),
            renderer.width - margin_x,
            status_y + renderer.sy(74),
        ),
        font_body,
        line_spacing=renderer.sy(3),
    )

    msg_h = renderer.sy(220)
    msg_top = renderer.height - renderer.sy(40) - msg_h
    renderer._draw_message_box(draw, margin_x, msg_top, content_w, msg_h)
    draw.text(
        (margin_x + renderer.sx(10), msg_top + renderer.sy(8)),
        t(data.lang, "message"),
        font=font_small,
        fill="black",
    )

    msg = data.message.strip() if data.message else t(data.lang, "default_message")
    renderer._draw_wrapped_text(
        draw,
        msg,
        (
            margin_x + renderer.sx(10),
            msg_top + renderer.sy(28),
            renderer.width - margin_x - renderer.sx(10),
            msg_top + msg_h - renderer.sy(10),
        ),
        font=font_message,
        line_spacing=renderer.sy(3),
    )

    return img


def _render_today_with_image_landscape(
    renderer: "SmartWizArtRenderer",
    data: "TodayPanelData",
    img: Image.Image,
) -> Image.Image:
    renderer._draw_side_image(
        img,
        data,
    )
    draw = ImageDraw.Draw(img)

    panel_x = renderer.sx(18)
    panel_y = renderer.sy(18)
    panel_w = renderer.sx(260)
    panel_h = renderer.height - renderer.sy(36)

    draw.rounded_rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
        radius=renderer.sf(18),
        fill=(249, 247, 241),
        outline=(75, 75, 75),
        width=max(1, renderer.sf(1)),
    )

    font_date = renderer._load_font(renderer.sf(20), bold=True)
    font_weekday = renderer._load_font(renderer.sf(18), bold=False)
    _, font_weather_emoji = renderer._load_font_pair(renderer.sf(34), bold=True)
    font_temp = renderer._load_font(renderer.sf(24), bold=True)
    font_section = renderer._load_font(renderer.sf(15), bold=True)
    font_body = renderer._load_font(renderer.sf(16), bold=False)
    font_small = renderer._load_font(renderer.sf(13), bold=False)
    font_message = renderer._load_font(renderer.sf(16), bold=False)

    margin_x = panel_x + renderer.sx(16)
    right_x = panel_x + panel_w - renderer.sx(16)
    content_w = panel_w - renderer.sx(32)

    # 日付ヘッダ
    date_y = panel_y + renderer.sy(12)
    # それぞれのサイズ取得
    date_bbox = draw.textbbox((0, 0), data.date, font=font_date)
    weekday_bbox = draw.textbbox((0, 0), data.weekday, font=font_weekday)
    date_w = date_bbox[2] - date_bbox[0]
    weekday_w = weekday_bbox[2] - weekday_bbox[0]
    gap = renderer.sx(8)
    total_w = date_w + gap + weekday_w
    # 中央位置から左端を算出
    start_x = panel_x + (panel_w - total_w) // 2
    # 描画
    draw.text((start_x, date_y), data.date, font=font_date, fill="black")
    weekday_x = start_x + date_w + gap
    draw.text(
        (weekday_x, date_y + renderer.sy(4)),
        data.weekday,
        font=font_weekday,
        fill="black",
    )

    band_y = panel_y + renderer.sy(48)
    renderer._draw_season_band(draw, margin_x, band_y, content_w, renderer.sy(30))

    weather_y = panel_y + renderer.sy(84)
    icon = renderer._weather_icon(data.weather)
    label = renderer._weather_label(data.weather)
    draw.text((margin_x, weather_y), icon, font=font_weather_emoji, fill="black")
    draw.text(
        (margin_x + renderer.sx(46), weather_y + renderer.sy(22)),
        label,
        font=font_small,
        fill="black",
    )

    temp_text = data.temperature
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_temp)
    temp_w = temp_bbox[2] - temp_bbox[0]
    draw.text(
        (right_x - temp_w, weather_y - renderer.sy(5)),
        temp_text,
        font=font_temp,
        fill="black",
    )

    rain_y = weather_y + renderer.sy(40)
    if data.rain:
        renderer._draw_text_in_box(
            draw,
            data.rain,
            (margin_x, rain_y, right_x, rain_y + renderer.sy(30)),
            font_small,
            valign="center",
            line_spacing=renderer.sy(3),
            ellipsis=True,
        )

    renderer._draw_rule(draw, margin_x, panel_y + renderer.sy(160), content_w)

    section_y = panel_y + renderer.sy(176)
    draw.text(
        (margin_x, section_y),
        t(data.lang, "today_schedule"),
        font=font_section,
        fill="black",
    )

    item_y = section_y + renderer.sy(24)
    max_schedule = 2
    for item in list(data.schedule)[:max_schedule]:
        renderer._draw_bullet_line(
            draw, margin_x + renderer.sx(2), item_y, item, font_body
        )
        item_y += renderer.sy(26)

    if not data.schedule:
        draw.text(
            (margin_x + renderer.sx(2), item_y),
            t(data.lang, "no_schedule"),
            font=font_body,
            fill="black",
        )

    renderer._draw_rule(draw, margin_x, panel_y + renderer.sy(265), content_w)

    status_y = panel_y + renderer.sy(281)
    draw.text(
        (margin_x, status_y), t(data.lang, "home"), font=font_section, fill="black"
    )

    status_text = (
        "   ".join(data.home_status[:3])
        if data.home_status
        else t(data.lang, "no_status")
    )
    renderer._draw_wrapped_text(
        draw,
        status_text,
        (margin_x, status_y + renderer.sy(22), right_x, status_y + renderer.sy(62)),
        font_body,
        line_spacing=renderer.sy(3),
    )

    msg_top = panel_y + panel_h - renderer.sy(110)
    renderer._draw_message_box(
        draw,
        margin_x - renderer.sx(2),
        msg_top,
        content_w + renderer.sx(4),
        renderer.sy(74),
    )
    draw.text(
        (margin_x + renderer.sx(8), msg_top + renderer.sy(8)),
        t(data.lang, "message"),
        font=font_small,
        fill="black",
    )

    msg = data.message.strip() if data.message else t(data.lang, "default_message")
    renderer._draw_wrapped_text(
        draw,
        msg,
        (
            margin_x + renderer.sx(8),
            msg_top + renderer.sy(28),
            right_x,
            msg_top + renderer.sy(64),
        ),
        font=font_message,
        line_spacing=renderer.sy(3),
    )

    updated_y = msg_top + renderer.sy(80)
    renderer._draw_centered_text(
        draw,
        f"{data.updated} {t(data.lang, 'updated')}",
        (panel_x, updated_y, panel_x + panel_w, updated_y + renderer.sy(20)),
        font_small,
    )

    return img
