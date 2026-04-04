from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    MAX_PUSH_RETRY_AGE,
    PENDING_PUSH_STORE_KEY,
    PENDING_PUSH_STORE_VERSION,
    PUSH_STATE_WAITING,
)
from ..util.time import format_duration

if TYPE_CHECKING:
    from ..core.models import PanelData


def _pending_store(hass: HomeAssistant) -> Store:
    return Store(hass, PENDING_PUSH_STORE_VERSION, PENDING_PUSH_STORE_KEY)


async def _load_pending_pushes(hass: HomeAssistant) -> dict:
    data = await _pending_store(hass).async_load()
    if isinstance(data, dict):
        return data
    return {}


def get_runtime(hass: HomeAssistant, entry: ConfigEntry | None) -> dict | None:
    if entry is None:
        return None
    return hass.data.get(DOMAIN, {}).get("runtime", {}).get(entry.entry_id)


@callback
def set_push_loop_active(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    active: bool,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return
    runtime["push_loop_active"] = active
    notify_runtime_updated(hass, entry)


@callback
def notify_runtime_updated(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    for listener in list(runtime.get("listeners", [])):
        listener()


@callback
def set_output_info(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    filename: str,
    output_path: Path,
    panel_data: PanelData | None = None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_output_filename"] = filename
    runtime["last_image_path"] = str(output_path)

    ts = int(dt_util.now().timestamp())
    try:
        relative = output_path.relative_to(Path("/config/www"))
        runtime["last_image_url"] = f"/local/{relative.as_posix()}?v={ts}"
    except ValueError:
        runtime["last_image_url"] = None

    if all(
        hasattr(panel_data, attr)
        for attr in (
            "photo_preset",
            "resolved_photo_preset",
            "photo_avg_luma",
            "photo_contrast",
        )
    ):
        runtime["last_update_meta"] = {
            "photo_preset": getattr(panel_data, "photo_preset"),
            "resolved_photo_preset": getattr(panel_data, "resolved_photo_preset"),
            "photo_avg_luma": getattr(panel_data, "photo_avg_luma"),
            "photo_contrast": getattr(panel_data, "photo_contrast"),
        }

    notify_runtime_updated(hass, entry)


@callback
def set_push_started(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    s6_filename: str,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_push_started"] = dt_util.now()
    runtime["last_push_state"] = PUSH_STATE_WAITING
    runtime["last_push_error"] = None
    runtime["last_s6_filename"] = s6_filename
    notify_runtime_updated(hass, entry)


@callback
def set_pushing(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    s6_filename: str,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_push_state"] = "pushing"
    runtime["last_push_error"] = None
    runtime["last_s6_filename"] = s6_filename
    notify_runtime_updated(hass, entry)


@callback
def set_push_completed(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    s6_filename: str,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_push_completed"] = dt_util.now()
    runtime["last_push_state"] = "success"
    runtime["last_push_error"] = None
    runtime["last_s6_filename"] = s6_filename
    runtime["wake_probe_attempt"] = 0
    runtime["wake_probe_max"] = None
    runtime["push_retry_remaining"] = None
    runtime["push_retry_deadline"] = None
    runtime["push_requested_at"] = None
    runtime["push_retry_remaining_seconds"] = None
    notify_runtime_updated(hass, entry)


@callback
def set_push_failed(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    error: str,
    s6_filename: str | None = None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_push_state"] = "failed"
    runtime["last_push_error"] = error
    if s6_filename is not None:
        runtime["last_s6_filename"] = s6_filename
    notify_runtime_updated(hass, entry)


@callback
def set_push_expired(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    error: str,
    s6_filename: str | None = None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["last_push_state"] = "expired"
    runtime["last_push_error"] = error
    if s6_filename is not None:
        runtime["last_s6_filename"] = s6_filename
    notify_runtime_updated(hass, entry)


@callback
def clear_retry_runtime(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime:
        return

    runtime["wake_probe_attempt"] = 0
    runtime["wake_probe_max"] = None
    runtime["push_retry_remaining"] = None
    runtime["push_retry_deadline"] = None
    runtime["push_requested_at"] = None
    runtime["push_retry_remaining_seconds"] = None
    notify_runtime_updated(hass, entry)


async def update_retry_runtime(
    hass: HomeAssistant,
    entry: ConfigEntry | None,
    *,
    attempt_no: int | None = None,
    max_probe_count: int | None = None,
) -> None:
    runtime = get_runtime(hass, entry)
    if not runtime or entry is None:
        return

    if attempt_no is not None:
        runtime["wake_probe_attempt"] = attempt_no
    if max_probe_count is not None:
        runtime["wake_probe_max"] = max_probe_count

    data = await _load_pending_pushes(hass)
    pending = data.get(entry.entry_id)
    if not isinstance(pending, dict):
        runtime["push_retry_remaining"] = None
        runtime["push_retry_deadline"] = None
        runtime["push_requested_at"] = None
        runtime["push_retry_remaining_seconds"] = None
        return

    requested_at_raw = pending.get("requested_at")
    if not requested_at_raw:
        runtime["push_retry_remaining"] = None
        runtime["push_retry_deadline"] = None
        runtime["push_requested_at"] = None
        runtime["push_retry_remaining_seconds"] = None
        return

    try:
        requested_at = dt_util.parse_datetime(requested_at_raw)
    except Exception:
        requested_at = None

    if requested_at is None:
        runtime["push_retry_remaining"] = None
        runtime["push_retry_deadline"] = None
        runtime["push_requested_at"] = None
        runtime["push_retry_remaining_seconds"] = None
        return

    deadline = requested_at + MAX_PUSH_RETRY_AGE
    remaining = deadline - dt_util.now()

    runtime["push_retry_remaining"] = format_duration(remaining)
    runtime["push_retry_remaining_seconds"] = max(0, int(remaining.total_seconds()))
    runtime["push_retry_deadline"] = deadline.isoformat()
    runtime["push_requested_at"] = requested_at.isoformat()
