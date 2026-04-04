from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    get_device_base_dir,
    get_device_cache_dir,
    get_device_key_dir,
    get_device_state_dir,
)
from .core.register import SmartWizArtRegistrationError, unregister_device_sync
from .service import async_register_services
from .service_helpers import get_push_manager

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _check_keys(keys: Path) -> None:
    if not (keys / "app_private.der").exists():
        _LOGGER.warning(
            "No key files found in %s. "
            "Run register_device to create registration keys, or place app_private.der and epd_public_key.der manually to enable push.",
            keys,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN].setdefault("runtime", {})

    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})
    hass.data[DOMAIN].setdefault("runtime", {})

    hass.data[DOMAIN]["entries"][entry.entry_id] = entry
    hass.data[DOMAIN]["runtime"][entry.entry_id] = {
        "last_image_path": None,
        "last_image_url": None,
        "last_output_filename": None,
        "last_push_completed": None,
        "last_push_error": None,
        "last_push_started": None,
        "last_push_state": "idle",
        "last_s6_filename": None,
        "listeners": [],
        "push_loop_active": False,
        "push_requested_at": None,
        "push_retry_deadline": None,
        "push_retry_remaining": None,
        "push_retry_remaining_seconds": None,
        "wake_probe_attempt": 0,
        "wake_probe_max": None,
    }

    # --- device_id ---
    device_id = str(entry.data.get("device_id", "")).strip()
    if not device_id:
        raise ValueError("device_id is required")

    # --- paths ---
    base = get_device_base_dir(device_id)
    keys = get_device_key_dir(device_id)
    state = get_device_state_dir(device_id)
    cache = get_device_cache_dir(device_id)

    # --- create dirs (non-blocking) ---
    for p in (base, keys, state, cache):
        await hass.async_add_executor_job(_mkdir, p)

    await hass.async_add_executor_job(_check_keys, keys)

    # --- ensure device registry entry exists ---
    host = str(entry.data.get(CONF_HOST, "")).strip()
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        manufacturer="DISIGN Incorporated",
        model="SMARTWIZ+ art",
        name=entry.title or f"SMARTWIZ+ art ({device_id})",
        serial_number=device_id,
        configuration_url=f"http://{host}" if host else None,
    )

    # --- setup platforms ---
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- restore pending pushes (defer until HA startup is finished) ---
    push_manager = get_push_manager(hass)

    @callback
    def _restore_pending_pushes(_event=None) -> None:
        hass.async_create_task(
            push_manager.restore_pending_pushes(entry),
            name=f"{DOMAIN}_restore_pending_pushes_{entry.entry_id}",
        )

    if hass.is_running:
        _restore_pending_pushes()
    else:
        entry.async_on_unload(
            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                _restore_pending_pushes,
            )
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    push_manager = get_push_manager(hass)
    await push_manager.cancel_push(entry)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
        hass.data[DOMAIN]["runtime"].pop(entry.entry_id, None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    device_id = str(entry.data.get("device_id", "")).strip()
    host = str(entry.data.get("host", "")).strip()

    if not device_id or not host:
        return

    try:
        result = await hass.async_add_executor_job(
            unregister_device_sync,
            device_id,
            host,
        )
    except SmartWizArtRegistrationError as err:
        _LOGGER.warning(
            "SMARTWIZ+ art unregister during removal failed: entry_id=%s, device_id=%s, host=%s, error=%s",
            entry.entry_id,
            device_id,
            host,
            err,
        )
    except Exception:
        _LOGGER.exception(
            "Unexpected error while unregistering SMARTWIZ+ art during entry removal: entry_id=%s, device_id=%s, host=%s",
            entry.entry_id,
            device_id,
            host,
        )
    else:
        _LOGGER.info(
            "SMARTWIZ+ art unregister during removal completed: entry_id=%s, device_id=%s, status=%s",
            entry.entry_id,
            device_id,
            result.get("status"),
        )


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow manual removal of the SMARTWIZ+ art device from the device registry."""
    device_id = str(entry.data.get("device_id", "")).strip()
    if not device_id:
        return False

    return (DOMAIN, device_id) in device_entry.identifiers
