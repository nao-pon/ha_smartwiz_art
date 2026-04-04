from __future__ import annotations

from homeassistant.core import HomeAssistant

from ..render.loader import load_template_registry
from .models import PanelData
from .resolver import build_notice_panel_data, build_today_panel_data

_TEMPLATE_REGISTRY = load_template_registry()

SUPPORTED_TEMPLATES = {
    name: {
        "type": meta["type"],
        "orientation": meta["orientation"],
    }
    for name, meta in _TEMPLATE_REGISTRY.items()
}

_PANEL_BUILDERS = {
    "today": build_today_panel_data,
    "notice": build_notice_panel_data,
}


async def build_template_data(
    hass: HomeAssistant,
    template: str,
    theme: str,
    source_map: dict,
    variables: dict | None = None,
) -> PanelData:
    meta = SUPPORTED_TEMPLATES.get(template)
    if meta is None:
        raise ValueError(f"Unsupported template: {template}")

    if variables is None:
        variables = {}

    variables["theme"] = theme
    variables["template"] = template
    variables.setdefault("lang", "ja")

    template_type = meta["type"]
    builder = _PANEL_BUILDERS.get(template_type)
    if builder is None:
        raise ValueError(f"Unsupported template type: {template_type}")

    return await builder(hass, source_map, variables)
