from __future__ import annotations

STRINGS = {
    "ja": {
        "rain": "降水",
        "today_schedule": "今日の予定",
        "no_schedule": "予定はありません",
        "home": "HOME",
        "no_status": "状態情報なし",
        "notice": "お知らせ",
        "message": "メッセージ",
        "default_message": "今日もよい一日を。",
        "updated": "更新",
        "unknown": "不明",
        "locked": "施錠",
        "unlocked": "未施錠",
        "front_door": "玄関",
        "indoor": "室内",
        "weather.sunny": "晴れ",
        "weather.clear-night": "晴れ(夜)",
        "weather.partlycloudy": "晴れ時々くもり",
        "weather.cloudy": "くもり",
        "weather.fog": "霧",
        "weather.rainy": "雨",
        "weather.pouring": "強い雨",
        "weather.lightning": "雷",
        "weather.lightning-rainy": "雷雨",
        "weather.snowy": "雪",
        "weather.snowy-rainy": "みぞれ",
        "weather.hail": "ひょう",
        "weather.windy": "強風",
        "weather.windy-variant": "風あり",
        "weather.exceptional": "異常気象",
    },
    "en": {
        "rain": "Rain",
        "today_schedule": "Today's Schedule",
        "no_schedule": "No schedule",
        "home": "HOME",
        "no_status": "No status",
        "notice": "Notice",
        "message": "Message",
        "default_message": "Have a wonderful day.",
        "updated": "Updated",
        "unknown": "Unknown",
        "locked": "Locked",
        "unlocked": "Unlocked",
        "front_door": "Front Door",
        "indoor": "Indoor",
        "weather.sunny": "Sunny",
        "weather.clear-night": "Clear Night",
        "weather.partlycloudy": "Partly Cloudy",
        "weather.cloudy": "Cloudy",
        "weather.fog": "Fog",
        "weather.rainy": "Rain",
        "weather.pouring": "Heavy Rain",
        "weather.lightning": "Lightning",
        "weather.lightning-rainy": "Thunderstorm",
        "weather.snowy": "Snow",
        "weather.snowy-rainy": "Sleet",
        "weather.hail": "Hail",
        "weather.windy": "Windy",
        "weather.windy-variant": "Breezy",
        "weather.exceptional": "Exceptional",
    },
}


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return "ja"
    return str(lang).strip().lower().split("-", 1)[0] or "ja"


def t(lang: str | None, key: str, default: str | None = None) -> str:
    normalized = normalize_lang(lang)
    table = STRINGS.get(normalized, STRINGS["ja"])
    if key in table:
        return table[key]
    if default is not None:
        return default
    return STRINGS["ja"].get(key, key)
