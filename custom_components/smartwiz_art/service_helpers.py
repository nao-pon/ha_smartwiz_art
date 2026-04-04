from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    DEFAULT_FILENAME,
    DEFAULT_HEIGHT,
    DEFAULT_THEME,
    DEFAULT_WIDTH,
    DOMAIN,
    get_device_cache_dir,
)

if TYPE_CHECKING:
    from .core.models import PanelData

from .core.runtime import (
    clear_retry_runtime,
    get_runtime,
    notify_runtime_updated,
    set_output_info,
    set_push_completed,
    set_push_expired,
    set_push_failed,
    set_push_loop_active,
    set_push_started,
    set_pushing,
    update_retry_runtime,
)
from .core.templates import SUPPORTED_TEMPLATES, build_template_data
from .image.converter import SmartWizArtConvertError
from .push_manager import PushManager, PushRuntimeHooks
from .render.renderer import SmartWizArtRenderer

_LOGGER = logging.getLogger(__name__)

SOURCE_KEYS = (
    "weather",
    "high_temp",
    "low_temp",
    "rain",
    "calendar",
    "schedule",
    "indoor_temp",
    "front_lock",
    "home_status",
    "message",
    "image_path",
)


def get_push_manager(hass: HomeAssistant) -> PushManager:
    manager = hass.data[DOMAIN].get("push_manager")
    if manager is None:
        manager = PushManager(
            hass,
            PushRuntimeHooks(
                set_push_loop_active=set_push_loop_active,
                notify_runtime_updated=notify_runtime_updated,
                get_runtime=get_runtime,
                set_push_started=set_push_started,
                set_pushing=set_pushing,
                set_push_completed=set_push_completed,
                set_push_failed=set_push_failed,
                set_push_expired=set_push_expired,
                clear_retry_runtime=clear_retry_runtime,
                update_retry_runtime=update_retry_runtime,
            ),
        )
        hass.data[DOMAIN]["push_manager"] = manager
    return manager


def build_source_spec(call_data: dict, key: str):
    entity_id = call_data.get(f"{key}_entity")
    attribute = call_data.get(f"{key}_attribute", "")

    if not entity_id:
        return None

    if attribute:
        return {
            "entity_id": entity_id,
            "attribute": attribute,
        }

    return entity_id


def merge_explicit_source_fields(call_data: dict, source_map: dict) -> dict:
    merged = dict(source_map)

    for key in SOURCE_KEYS:
        spec = build_source_spec(call_data, key)
        if spec is not None:
            merged[key] = spec

    return merged


def normalize_ha_device_ids(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        ids = value
    else:
        ids = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in ids:
        device_id = str(item).strip()
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        normalized.append(device_id)
    return normalized


def entry_dimensions(
    entry: ConfigEntry | None, template: str | None = None
) -> tuple[int, int]:
    width = DEFAULT_WIDTH
    height = DEFAULT_HEIGHT

    if entry is not None:
        width = int(entry.data.get("width", DEFAULT_WIDTH))
        height = int(entry.data.get("height", DEFAULT_HEIGHT))

    if template:
        template_spec = SUPPORTED_TEMPLATES.get(template, {})
        if template_spec.get("orientation") == "portrait":
            width, height = height, width

    return width, height


@callback
def warn_if_mixed_render_dimensions(
    entries: list[ConfigEntry],
    template: str,
) -> None:
    if len(entries) <= 1:
        return

    dims_map: dict[tuple[int, int], list[str]] = {}
    for entry in entries:
        dims = entry_dimensions(entry, template)
        dims_map.setdefault(dims, []).append(entry.entry_id)

    if len(dims_map) <= 1:
        return

    _LOGGER.warning(
        "SMARTWIZ+ art mixed render dimensions detected for template=%s: %s. "
        "Current service call renders once using the first selected device dimensions.",
        template,
        {f"{w}x{h}": ids for (w, h), ids in dims_map.items()},
    )


def resolve_entries(hass: HomeAssistant, call: ServiceCall) -> list[ConfigEntry]:
    entries: dict[str, ConfigEntry] = hass.data.get(DOMAIN, {}).get("entries", {})

    ha_device_ids = normalize_ha_device_ids(call.data.get("ha_device_id"))
    if ha_device_ids:
        device_registry = dr.async_get(hass)
        matched_entries: list[ConfigEntry] = []
        seen_entry_ids: set[str] = set()

        for ha_device_id in ha_device_ids:
            device = device_registry.async_get(ha_device_id)
            if device is None:
                raise vol.Invalid(f"Unknown Home Assistant device_id: {ha_device_id}")

            smartwiz_device_id = None
            for domain, identifier in device.identifiers:
                if domain == DOMAIN:
                    smartwiz_device_id = str(identifier)
                    break

            if not smartwiz_device_id:
                raise vol.Invalid(
                    f"No SMARTWIZ+ art identifier found for Home Assistant device_id: {ha_device_id}"
                )

            matched = [
                entry
                for entry in entries.values()
                if str(entry.data.get("device_id") or "") == smartwiz_device_id
            ]

            if not matched:
                raise vol.Invalid(
                    f"No SMARTWIZ+ art entry matched Home Assistant device_id: {ha_device_id}"
                )

            if len(matched) > 1:
                raise vol.Invalid(
                    f"Multiple SMARTWIZ+ art entries matched Home Assistant device_id: {ha_device_id}"
                )

            entry = matched[0]
            if entry.entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry.entry_id)
            matched_entries.append(entry)

        return matched_entries

    if len(entries) == 1:
        return [next(iter(entries.values()))]

    if len(entries) == 0:
        return []

    raise vol.Invalid(
        "Multiple SMARTWIZ+ art entries are configured; please specify ha_device_id"
    )


def resolve_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry | None:
    entries = resolve_entries(hass, call)
    return entries[0] if entries else None


def resolve_host_and_device_id(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[ConfigEntry, str, str]:
    entry = resolve_entry(hass, call)
    if entry is None:
        raise vol.Invalid("No SMARTWIZ+ art entry is configured")

    device_id = str(entry.data.get("device_id", "")).strip()
    if not device_id:
        raise vol.Invalid("device_id is required")

    host = str(call.data.get("host") or entry.data.get("host") or "").strip()
    if not host:
        raise vol.Invalid("host is required")

    return entry, host, device_id


async def render_output_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
    entries: list[ConfigEntry],
    output_image,
) -> tuple[Path, PanelData]:
    if not entries:
        raise vol.Invalid("No target device found")

    render_entry = entries[0]

    template, theme, source_map, variables = _resolve_render_options(call, render_entry)

    panel_data = await build_template_data(
        hass=hass,
        template=template,
        theme=theme,
        source_map=source_map,
        variables=variables,
    )

    image_path = getattr(panel_data, "image_path", "")
    if image_path and hasattr(panel_data, "photo_preset"):
        photo_preset = resolve_photo_preset(
            image_path=image_path,
            service_preset=call.data.get("photo_preset"),
            default_preset="auto",
        )
        setattr(panel_data, "photo_preset", photo_preset)

    width, height = entry_dimensions(render_entry, template)
    warn_if_mixed_render_dimensions(entries, template)

    template_spec = SUPPORTED_TEMPLATES.get(template, {})
    render_type = template_spec.get("type", "today")

    renderer = SmartWizArtRenderer(width=width, height=height)
    image = await hass.async_add_executor_job(renderer.render, render_type, panel_data)

    filename = call.data.get("filename", DEFAULT_FILENAME)
    output_path = await output_image(image, filename, entries, panel_data=panel_data)
    return output_path, panel_data


async def ensure_dir(hass: HomeAssistant, path: Path) -> None:
    await hass.async_add_executor_job(partial(path.mkdir, parents=True, exist_ok=True))


async def push_file_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
    input_path: Path | None = None,
    convert_options: dict | None = None,
) -> tuple[list, Path, str]:
    convert_options = dict(convert_options or {})
    push_manager = get_push_manager(hass)

    entries = resolve_entries(hass, call)

    input_path = input_path if input_path else Path(call.data["input_path"])
    if not input_path.exists():
        raise vol.Invalid(f"Input file not found: {input_path}")

    s6_filename = call.data.get("s6_filename")
    if not s6_filename:
        s6_filename = f"{input_path.stem}.s6"

    dither = bool(convert_options.get("dither", True))

    convert_options.update(
        {
            "dither": dither,
        }
    )

    for entry in entries:
        device_id = _resolve_device_id(entry)
        host = _resolve_host(entry)

        try:
            s6_dir = get_device_cache_dir(device_id)
            await ensure_dir(hass, s6_dir)
            s6_path = s6_dir / s6_filename

            await push_manager.convert_png_to_s6(input_path, s6_path, convert_options)
            set_output_info(hass, entry, input_path.name, input_path)

            await push_manager.enqueue_push(
                entry=entry,
                host=host,
                device_id=device_id,
                s6_filename=s6_filename,
            )

        except SmartWizArtConvertError as err:
            set_push_failed(hass, entry, str(err), s6_filename)
            await push_manager.clear_pending_push(entry)
            raise vol.Invalid(str(err)) from err

    return (entries, input_path, s6_filename)


def _resolve_render_options(
    call: ServiceCall,
    render_entry: ConfigEntry | None,
) -> tuple[str, str, dict, dict]:
    entry_source_map = {}
    entry_template = "today"
    entry_theme = DEFAULT_THEME

    if render_entry and render_entry.options:
        entry_source_map = render_entry.options.get("source_map", {})
        entry_template = render_entry.options.get("default_template", "today")
        entry_theme = render_entry.options.get("default_theme", DEFAULT_THEME)

    template = call.data.get("template", entry_template or "today")
    if template not in SUPPORTED_TEMPLATES:
        raise vol.Invalid(f"Unsupported template: {template}")

    theme = call.data.get("theme", entry_theme or DEFAULT_THEME)

    source_map = dict(entry_source_map)
    source_map.update(call.data.get("source_map", {}))
    source_map = merge_explicit_source_fields(call.data, source_map)

    variables = dict(call.data.get("variables", {}))
    variables.setdefault("lang", call.data.get("lang", "ja"))

    return template, theme, source_map, variables


def _resolve_device_id(entry: ConfigEntry | None) -> str:
    if entry is None:
        raise vol.Invalid("No SMARTWIZ+ art config entry is configured")

    device_id = entry.data.get("device_id", "")
    if not device_id:
        raise vol.Invalid("device_id is not configured in this entry")

    return str(device_id)


def _resolve_host(entry: ConfigEntry | None) -> str:
    if entry is None:
        return ""
    host = entry.data.get("host")
    return str(host) if host else ""


def parse_image_options(filename: str) -> dict[str, str]:
    """
    ファイル名から埋め込みオプションを読む。

    例:
      family__p=soft__d=off.jpg
      -> {"p": "soft", "d": "off"}
    """
    stem = Path(filename).stem
    parts = stem.split("__")

    opts: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            opts[key] = value

    return opts


VALID_PHOTO_PRESETS = {"auto", "natural", "vivid", "soft"}


def normalize_photo_preset(
    value: str | None,
    default: str = "auto",
) -> str:
    if not value:
        return default
    key = str(value).strip().lower()
    return key if key in VALID_PHOTO_PRESETS else default


def resolve_photo_preset(
    image_path: str | None,
    service_preset: str | None,
    default_preset: str = "auto",
) -> str:
    """
    優先順位:
      1. サービス引数 photo_preset
      2. ファイル名埋め込み pp=
      3. デフォルト
    """
    if service_preset:
        return normalize_photo_preset(service_preset, default=default_preset)

    if image_path:
        opts = parse_image_options(image_path)
        embedded = opts.get("pp") or opts.get("photo_preset")
        if embedded:
            return normalize_photo_preset(embedded, default=default_preset)

    return default_preset


def resolve_dither(
    image_path: str | None,
    service_dither: bool | None,
    default_dither: bool = True,
) -> bool:
    """
    優先順位:
      1. サービス引数
      2. ファイル名埋め込み d=
      3. デフォルト
    """
    if service_dither is not None:
        return bool(service_dither)

    if image_path:
        opts = parse_image_options(image_path)
        if "d" in opts:
            value = opts["d"].strip().lower()
            if value in ("on", "true", "1", "yes"):
                return True
            if value in ("off", "false", "0", "no"):
                return False

    return default_dither


VALID_IMAGE_FIT_MODES = {"crop", "fit", "stretch"}


def normalize_image_fit(
    value: str | None,
    default: str = "crop",
) -> str:
    if not value:
        return default
    key = str(value).strip().lower()
    return key if key in VALID_IMAGE_FIT_MODES else default


def resolve_image_fit(
    image_path: str | None,
    service_image_fit: str | None,
    default_image_fit: str = "crop",
) -> str:
    """
    優先順位:
      1. サービス引数 image_fit
      2. ファイル名埋め込み fit= / image_fit= / f=
      3. デフォルト
    """
    if service_image_fit:
        return normalize_image_fit(service_image_fit, default=default_image_fit)

    if image_path:
        opts = parse_image_options(image_path)
        embedded = opts.get("fit") or opts.get("image_fit") or opts.get("f")
        if embedded:
            return normalize_image_fit(embedded, default=default_image_fit)

    return default_image_fit
