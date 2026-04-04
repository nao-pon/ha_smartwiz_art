from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..translations.render import t
from .models import NoticePanelData, TodayPanelData


def get_state_str(hass: HomeAssistant, entity_id: str, default: str = "") -> str:
    state = hass.states.get(entity_id)
    if state is None:
        return default
    return state.state


def get_attr(hass: HomeAssistant, entity_id: str, attr: str, default=None):
    state = hass.states.get(entity_id)
    if state is None:
        return default
    return state.attributes.get(attr, default)


def _parse_source_spec(source) -> tuple[str | None, str | None]:
    """source_map の値を正規化する。

    対応形式:
      - "sensor.living_temp"
      - {"entity_id": "sensor.living_temp"}
      - {"entity_id": "weather.home", "attribute": "forecast.0.temperature"}
    """
    if isinstance(source, str):
        return source, None

    if isinstance(source, dict):
        entity_id = source.get("entity_id")
        attribute = source.get("attribute")
        return entity_id, attribute

    return None, None


def _resolve_path(value: Any, path: str | None, default=None):
    """dict/list に対して dot path を辿る。

    例:
      forecast.0.temperature
    """
    if path in (None, ""):
        return value

    current = value
    for part in str(path).split("."):
        if current is None:
            return default

        if isinstance(current, list):
            if not part.isdigit():
                return default
            index = int(part)
            if index < 0 or index >= len(current):
                return default
            current = current[index]
            continue

        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue

        return default

    return current


def get_source_value(
    hass: HomeAssistant,
    source,
    default=None,
):
    """source_map の指定に応じて state または attribute を返す。"""
    entity_id, attribute = _parse_source_spec(source)
    if not entity_id:
        return default

    state = hass.states.get(entity_id)
    if state is None:
        return default

    if not attribute:
        return state.state

    return _resolve_path(state.attributes, attribute, default)


def get_source_str(
    hass: HomeAssistant,
    source,
    default: str = "",
) -> str:
    value = get_source_value(hass, source, default)
    if value is None:
        return default
    return str(value)


def resolve_date_and_weekday(variables: dict) -> tuple[str, str, str]:
    now = dt_util.now()

    updated_text = now.strftime("%-m.%-d %H:%M")

    date_text = variables.get("date")
    if not date_text:
        date_text = now.strftime("%Y / %-m / %-d")

    weekday_text = variables.get("weekday")
    if not weekday_text:
        weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekday_text = weekday_names[now.weekday()]

    return date_text, weekday_text, updated_text


def _normalize_lines(value) -> list[str]:
    """文字列 or 配列を行リストに揃える。"""
    if value is None:
        return []

    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]

    if isinstance(value, tuple):
        return [str(v) for v in value if v not in (None, "")]

    text = str(value).strip()
    if not text:
        return []

    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]

    return [text]


def is_num(s):
    try:
        float(s)
    except ValueError:
        return False
    else:
        return True


async def build_today_panel_data(
    hass: HomeAssistant,
    source_map: dict,
    variables: dict | None = None,
) -> TodayPanelData:
    variables = variables or {}

    date_text, weekday_text, updated_text = resolve_date_and_weekday(variables)

    weather_source = source_map.get("weather")
    calendar_source = source_map.get("calendar")
    indoor_temp_source = source_map.get("indoor_temp")
    high_temp_source = source_map.get("high_temp")
    low_temp_source = source_map.get("low_temp")
    front_lock_source = source_map.get("front_lock")
    rain_source = source_map.get("rain")
    schedule_source = source_map.get("schedule")
    home_status_source = source_map.get("home_status")
    message_source = source_map.get("message")
    image_path_source = source_map.get("image_path")

    lang = variables.get("lang", "ja")

    weather = (
        get_source_str(hass, weather_source, t(lang, "unknown"))
        if weather_source
        else t(lang, "unknown")
    )

    if high_temp_source and low_temp_source:
        high_temp = get_source_str(hass, high_temp_source, "-")
        low_temp = get_source_str(hass, low_temp_source, "-")
        if is_num(high_temp):
            high_temp = round(float(high_temp))
        if is_num(low_temp):
            low_temp = round(float(low_temp))
        temperature = f"{high_temp} / {low_temp}℃"
    else:
        temperature = "-"

    rain = ""
    if rain_source:
        rain_value = get_source_value(hass, rain_source, "")
        if rain_value not in (None, ""):
            rain = f"{rain_value}"
    elif weather_source:
        # 既存互換: weather の forecast[0].precipitation_probability を見る
        rain_value = get_source_value(
            hass,
            {
                "entity_id": _parse_source_spec(weather_source)[0],
                "attribute": "forecast.0.precipitation_probability",
            },
            None,
        )
        if rain_value is not None:
            rain = f"{rain_value}%"

    schedule = []
    if schedule_source:
        schedule.extend(_normalize_lines(get_source_value(hass, schedule_source, [])))
    elif calendar_source:
        schedule.extend(_normalize_lines(get_source_value(hass, calendar_source, "")))

    home_status = []

    if home_status_source:
        home_status.extend(
            _normalize_lines(get_source_value(hass, home_status_source, []))
        )
    else:
        if front_lock_source:
            lock_state = get_source_str(hass, front_lock_source, "unknown")
            label = t(lang, "locked") if lock_state == "locked" else t(lang, "unlocked")
            home_status.append(f"{t(lang, 'front_door')}: {label}")

        if indoor_temp_source:
            home_status.append(
                f"{t(lang, 'indoor')}: {get_source_str(hass, indoor_temp_source, '-')}℃"
            )

    home_status.extend(_normalize_lines(variables.get("home_status")))

    message = ""
    if message_source:
        message = get_source_str(hass, message_source, "")

    image_path = ""
    if image_path_source:
        image_path = get_source_str(hass, image_path_source, "")

    return TodayPanelData(
        date=date_text,
        weekday=weekday_text,
        weather=variables.get("weather", weather),
        temperature=variables.get("temperature", temperature),
        rain=variables.get("rain", rain),
        schedule=variables.get("schedule", schedule),
        home_status=home_status,
        message=variables.get("message", message),
        theme=variables.get("theme", "washi"),
        template=variables.get("template", "today"),
        image_path=variables.get("image_path", image_path),
        photo_preset=variables.get("photo_preset", "natural"),
        updated=updated_text,
        lang=lang,
    )


async def build_notice_panel_data(
    hass: HomeAssistant,
    source_map: dict,
    variables: dict | None = None,
) -> NoticePanelData:
    variables = variables or {}

    date_text, weekday_text, updated_text = resolve_date_and_weekday(variables)
    lang = variables.get("lang", "ja")

    title_source = source_map.get("title")
    body_source = source_map.get("body")
    level_source = source_map.get("level")
    icon_source = source_map.get("icon")
    message_source = source_map.get("message")

    title = variables.get("title")
    if title is None and title_source:
        title = get_source_str(hass, title_source, "")

    body = variables.get("body")
    if body is None and body_source:
        body = get_source_str(hass, body_source, "")
    if not body and message_source:
        body = get_source_str(hass, message_source, "")
    if not body:
        body = variables.get("message", "")

    level = variables.get("level")
    if level is None and level_source:
        level = get_source_str(hass, level_source, "info")
    if not level:
        level = "info"

    icon = variables.get("icon")
    if icon is None and icon_source:
        icon = get_source_str(hass, icon_source, "")
    if not icon:
        icon = ""

    return NoticePanelData(
        title=title,
        body=body,
        date=date_text,
        weekday=weekday_text,
        level=level,
        icon=icon,
        theme=variables.get("theme", "washi"),
        template=variables.get("template", "notice"),
        updated=updated_text,
        lang=lang,
    )
