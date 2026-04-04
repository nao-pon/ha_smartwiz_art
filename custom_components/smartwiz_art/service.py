from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_FILENAME,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_THEME,
    DOMAIN,
    SERVICE_PUSH_FILE,
    SERVICE_REGISTER_DEVICE,
    SERVICE_RENDER_TODAY,
    SERVICE_UNREGISTER_DEVICE,
    SERVICE_UPDATE,
    SERVICE_UPDATE_AND_PUSH,
    get_device_key_dir,
)
from .core.models import PanelData, TodayPanelData
from .core.register import (
    SmartWizArtRegistrationError,
    register_device_sync,
    unregister_device_sync,
)
from .core.runtime import (
    set_output_info,
)
from .core.templates import SUPPORTED_TEMPLATES
from .render.renderer import SmartWizArtRenderer
from .service_helpers import (
    ensure_dir,
    entry_dimensions,
    push_file_from_call,
    render_output_from_call,
    resolve_dither,
    resolve_entries,
    resolve_host_and_device_id,
    resolve_image_fit,
    resolve_photo_preset,
    warn_if_mixed_render_dimensions,
)

_LOGGER = logging.getLogger(__name__)

RENDER_TODAY_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): vol.Any(cv.string, [cv.string]),
        vol.Optional("filename", default=DEFAULT_FILENAME): cv.string,
        vol.Required("date"): cv.string,
        vol.Required("weekday"): cv.string,
        vol.Required("weather"): cv.string,
        vol.Required("temperature"): cv.string,
        vol.Optional("rain", default=""): cv.string,
        vol.Optional("schedule", default=[]): vol.All(list, [cv.string]),
        vol.Optional("home_status", default=[]): vol.All(list, [cv.string]),
        vol.Optional("message", default=""): cv.string,
        vol.Optional("theme", default=DEFAULT_THEME): cv.string,
        vol.Optional("lang", default="ja"): vol.In(["ja", "en"]),
        vol.Optional("template", default="today"): cv.string,
    }
)

UPDATE_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): vol.Any(cv.string, [cv.string]),
        vol.Optional("template", default="today"): cv.string,
        vol.Optional("filename", default=DEFAULT_FILENAME): cv.string,
        vol.Optional("source_map", default={}): dict,
        vol.Optional("variables", default={}): dict,
        vol.Optional("theme", default=DEFAULT_THEME): cv.string,
        vol.Optional("lang", default="ja"): vol.In(["ja", "en"]),
        vol.Optional("weather_entity"): cv.entity_id,
        vol.Optional("weather_attribute"): cv.string,
        vol.Optional("high_temp_entity"): cv.entity_id,
        vol.Optional("high_temp_attribute"): cv.string,
        vol.Optional("low_temp_entity"): cv.entity_id,
        vol.Optional("low_temp_attribute"): cv.string,
        vol.Optional("rain_entity"): cv.entity_id,
        vol.Optional("rain_attribute"): cv.string,
        vol.Optional("calendar_entity"): cv.entity_id,
        vol.Optional("calendar_attribute"): cv.string,
        vol.Optional("schedule_entity"): cv.entity_id,
        vol.Optional("schedule_attribute"): cv.string,
        vol.Optional("indoor_temp_entity"): cv.entity_id,
        vol.Optional("indoor_temp_attribute"): cv.string,
        vol.Optional("front_lock_entity"): cv.entity_id,
        vol.Optional("front_lock_attribute"): cv.string,
        vol.Optional("home_status_entity"): cv.entity_id,
        vol.Optional("home_status_attribute"): cv.string,
        vol.Optional("message_entity"): cv.entity_id,
        vol.Optional("message_attribute"): cv.string,
        vol.Optional("image_path_entity"): cv.entity_id,
        vol.Optional("image_path_attribute"): cv.string,
        vol.Optional("photo_preset"): cv.string,
        vol.Optional("dither"): cv.boolean,
    }
)

PUSH_FILE_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): vol.Any(cv.string, [cv.string]),
        vol.Required("input_path"): cv.string,
        vol.Optional("s6_filename"): cv.string,
        vol.Optional("image_fit", default="crop"): vol.In(["crop", "fit", "stretch"]),
        vol.Optional("photo_preset", default="auto"): vol.In(
            ["auto", "natural", "vivid", "soft"]
        ),
        vol.Optional("dither"): cv.boolean,
    }
)

UPDATE_AND_PUSH_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): vol.Any(cv.string, [cv.string]),
        vol.Optional("template", default="today"): cv.string,
        vol.Optional("theme", default=DEFAULT_THEME): cv.string,
        vol.Optional("lang", default="ja"): vol.In(["ja", "en"]),
        vol.Optional("filename", default=DEFAULT_FILENAME): cv.string,
        vol.Optional("s6_filename"): cv.string,
        vol.Optional("source_map", default={}): dict,
        vol.Optional("variables", default={}): dict,
        vol.Optional("weather_entity"): cv.entity_id,
        vol.Optional("weather_attribute"): cv.string,
        vol.Optional("high_temp_entity"): cv.entity_id,
        vol.Optional("high_temp_attribute"): cv.string,
        vol.Optional("low_temp_entity"): cv.entity_id,
        vol.Optional("low_temp_attribute"): cv.string,
        vol.Optional("rain_entity"): cv.entity_id,
        vol.Optional("rain_attribute"): cv.string,
        vol.Optional("calendar_entity"): cv.entity_id,
        vol.Optional("calendar_attribute"): cv.string,
        vol.Optional("schedule_entity"): cv.entity_id,
        vol.Optional("schedule_attribute"): cv.string,
        vol.Optional("indoor_temp_entity"): cv.entity_id,
        vol.Optional("indoor_temp_attribute"): cv.string,
        vol.Optional("front_lock_entity"): cv.entity_id,
        vol.Optional("front_lock_attribute"): cv.string,
        vol.Optional("home_status_entity"): cv.entity_id,
        vol.Optional("home_status_attribute"): cv.string,
        vol.Optional("message_entity"): cv.entity_id,
        vol.Optional("message_attribute"): cv.string,
        vol.Optional("image_path_entity"): cv.entity_id,
        vol.Optional("image_path_attribute"): cv.string,
        vol.Optional("photo_preset"): cv.string,
        vol.Optional("dither"): cv.boolean,
    }
)


REGISTER_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): cv.string,
        vol.Optional("host"): cv.string,
    }
)

UNREGISTER_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("ha_device_id"): cv.string,
        vol.Optional("host"): cv.string,
        vol.Optional("purge_local_keys", default=False): cv.boolean,
    }
)


async def async_register_services(hass: HomeAssistant) -> None:
    async def output_image(
        image,
        filename: str,
        entries: list[ConfigEntry] | None = None,
        panel_data: PanelData | None = None,
    ) -> Path:
        output_dir = Path(DEFAULT_OUTPUT_DIR)
        await ensure_dir(hass, output_dir)

        output_path = output_dir / filename
        await hass.async_add_executor_job(image.save, output_path)
        _LOGGER.info("SMARTWIZ+ art image rendered: %s", output_path)

        for entry in entries or []:
            set_output_info(hass, entry, filename, output_path, panel_data)
        return output_path

    async def handle_render_today(call: ServiceCall) -> None:
        entries = resolve_entries(hass, call)
        render_entry = entries[0] if entries else None

        template = call.data.get("template", "today")
        if template not in SUPPORTED_TEMPLATES:
            raise vol.Invalid(f"Unsupported template: {template}")

        width, height = entry_dimensions(render_entry, template)
        warn_if_mixed_render_dimensions(entries, template)

        render_data = TodayPanelData(
            date=call.data["date"],
            weekday=call.data["weekday"],
            weather=call.data["weather"],
            temperature=call.data["temperature"],
            rain=call.data.get("rain", ""),
            schedule=call.data.get("schedule", []),
            home_status=call.data.get("home_status", []),
            message=call.data.get("message", ""),
            theme=call.data.get("theme", "washi"),
            template=template,
            photo_preset="auto",
            lang=call.data.get("lang", "ja"),
        )
        template_spec = SUPPORTED_TEMPLATES.get(render_data.template, {})

        renderer = SmartWizArtRenderer(width=width, height=height)
        render_type = template_spec.get("type", "today")

        image = await hass.async_add_executor_job(
            renderer.render, render_type, render_data
        )

        await output_image(
            image,
            call.data.get("filename", DEFAULT_FILENAME),
            entries,
            panel_data=render_data,
        )

    async def handle_update(call: ServiceCall) -> None:
        entries = resolve_entries(hass, call)
        output_path, _ = await render_output_from_call(
            hass=hass,
            call=call,
            entries=entries,
            output_image=output_image,
        )
        _LOGGER.info("SMARTWIZ+ art update completed: %s", output_path)

    async def handle_push_file(call: ServiceCall) -> None:

        convert_options = {}
        if call.data["input_path"]:
            convert_options["dither"] = resolve_dither(
                image_path=call.data["input_path"],
                service_dither=call.data.get("dither"),
            )
            convert_options["image_fit"] = resolve_image_fit(
                image_path=call.data["input_path"],
                service_image_fit=call.data.get("image_fit"),
            )
            convert_options["photo_preset"] = resolve_photo_preset(
                image_path=call.data["input_path"],
                service_preset=call.data.get("photo_preset"),
                default_preset="auto",
            )

        (entries, input_path, s6_filename) = await push_file_from_call(
            hass=hass, call=call, convert_options=convert_options
        )
        _LOGGER.info(
            "SMARTWIZ+ art file push scheduled for %s device(s): %s -> %s",
            len(entries),
            input_path,
            s6_filename,
        )

    async def handle_update_and_push(call: ServiceCall) -> None:
        entries = resolve_entries(hass, call)

        input_path, today_data = await render_output_from_call(
            hass=hass,
            call=call,
            entries=entries,
            output_image=output_image,
        )

        convert_options = {}
        image_path = getattr(today_data, "image_path", "")
        if image_path:
            convert_options["dither"] = resolve_dither(
                image_path=image_path,
                service_dither=call.data.get("dither"),
            )

        _, output_path, s6_filename = await push_file_from_call(
            hass=hass,
            call=call,
            input_path=input_path,
            convert_options=convert_options,
        )

        _LOGGER.info(
            "SMARTWIZ+ art update_and_push scheduled for %s device(s): %s -> %s",
            len(entries),
            output_path,
            s6_filename,
        )

    async def handle_register_device(call: ServiceCall) -> None:
        entry, host, device_id = resolve_host_and_device_id(hass, call)
        await ensure_dir(hass, get_device_key_dir(device_id))

        try:
            result = await hass.async_add_executor_job(
                register_device_sync, device_id, host
            )
        except SmartWizArtRegistrationError as err:
            raise vol.Invalid(str(err)) from err

        _LOGGER.info(
            "SMARTWIZ+ art register completed: entry_id=%s, device_id=%s, status=%s",
            entry.entry_id,
            device_id,
            result.get("status"),
        )

    async def handle_unregister_device(call: ServiceCall) -> None:
        entry, host, device_id = resolve_host_and_device_id(hass, call)
        purge_local_keys = bool(call.data.get("purge_local_keys", False))

        try:
            result = await hass.async_add_executor_job(
                partial(
                    unregister_device_sync,
                    device_id,
                    host,
                    purge_local_keys=purge_local_keys,
                )
            )
        except SmartWizArtRegistrationError as err:
            raise vol.Invalid(str(err)) from err

        _LOGGER.info(
            "SMARTWIZ+ art unregister completed: entry_id=%s, device_id=%s, purge_local_keys=%s, status=%s",
            entry.entry_id,
            device_id,
            purge_local_keys,
            result.get("status"),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REGISTER_DEVICE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REGISTER_DEVICE,
            handle_register_device,
            schema=REGISTER_DEVICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UNREGISTER_DEVICE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UNREGISTER_DEVICE,
            handle_unregister_device,
            schema=UNREGISTER_DEVICE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RENDER_TODAY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RENDER_TODAY,
            handle_render_today,
            schema=RENDER_TODAY_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE,
            handle_update,
            schema=UPDATE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_PUSH_FILE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PUSH_FILE,
            handle_push_file,
            schema=PUSH_FILE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_AND_PUSH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_AND_PUSH,
            handle_update_and_push,
            schema=UPDATE_AND_PUSH_SCHEMA,
        )
