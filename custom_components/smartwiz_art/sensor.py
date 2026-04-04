from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PUSH_STATE_EXPIRED,
    PUSH_STATE_FAILED,
    PUSH_STATE_IDLE,
    PUSH_STATE_PUSHING,
    PUSH_STATE_SUCCESS,
    PUSH_STATE_WAITING,
    RUNTIME_LAST_PUSH_ERROR,
    RUNTIME_LAST_PUSH_STATE,
    RUNTIME_LAST_S6_FILENAME,
    RUNTIME_PUSH_LOOP_ACTIVE,
    RUNTIME_PUSH_REQUESTED_AT,
    RUNTIME_PUSH_RETRY_DEADLINE,
    RUNTIME_PUSH_RETRY_REMAINING,
    RUNTIME_PUSH_RETRY_REMAINING_SECONDS,
    RUNTIME_WAKE_PROBE_ATTEMPT,
    RUNTIME_WAKE_PROBE_MAX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            SmartWizArtLastPushSensor(hass, entry),
            SmartWizArtPushStatusSensor(hass, entry),
        ]
    )


class SmartWizArtBaseSensor(SensorEntity, RestoreEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.smartwiz_device_id = str(entry.data.get("device_id") or entry.entry_id)

    @property
    def device_info(self) -> DeviceInfo:
        host = str(self.entry.data.get(CONF_HOST, "")).strip()
        return DeviceInfo(
            identifiers={(DOMAIN, self.smartwiz_device_id)},
            name=self.entry.title,
            manufacturer="DISIGN Incorporated",
            model="SMARTWIZ+ art",
            serial_number=self.smartwiz_device_id,
            configuration_url=f"http://{host}" if host else None,
        )

    @property
    def _runtime(self) -> dict[str, Any]:
        return self.hass.data[DOMAIN]["runtime"][self.entry.entry_id]

    async def _async_restore_common_runtime(self, attrs: dict[str, Any]) -> None:
        runtime = self._runtime
        runtime["last_push_started"] = (
            dt_util.parse_datetime(attrs["last_push_started"])
            if attrs.get("last_push_started")
            else None
        )
        runtime[RUNTIME_LAST_PUSH_STATE] = attrs.get(
            "push_state", runtime.get(RUNTIME_LAST_PUSH_STATE, PUSH_STATE_IDLE)
        )
        runtime[RUNTIME_LAST_PUSH_ERROR] = attrs.get("last_push_error")
        runtime["last_output_filename"] = attrs.get("filename")
        runtime["last_image_url"] = attrs.get("image_url")
        runtime["last_image_path"] = attrs.get("image_path")
        runtime[RUNTIME_LAST_S6_FILENAME] = attrs.get("s6_filename")
        runtime[RUNTIME_WAKE_PROBE_ATTEMPT] = attrs.get(
            "wake_probe_attempt", runtime.get(RUNTIME_WAKE_PROBE_ATTEMPT, 0)
        )
        runtime[RUNTIME_WAKE_PROBE_MAX] = attrs.get(
            "wake_probe_max", runtime.get(RUNTIME_WAKE_PROBE_MAX)
        )
        runtime[RUNTIME_PUSH_RETRY_REMAINING] = attrs.get("push_retry_remaining")
        runtime[RUNTIME_PUSH_RETRY_REMAINING_SECONDS] = attrs.get(
            "push_retry_remaining_seconds"
        )
        runtime[RUNTIME_PUSH_RETRY_DEADLINE] = attrs.get("push_retry_deadline")
        runtime[RUNTIME_PUSH_REQUESTED_AT] = attrs.get("push_requested_at")
        if attrs.get("photo_preset"):
            runtime["last_update_meta"] = {
                "photo_preset": attrs.get("photo_preset"),
                "resolved_photo_preset": attrs.get("resolved_photo_preset"),
                "photo_avg_luma": attrs.get("photo_avg_luma"),
                "photo_contrast": attrs.get("photo_contrast"),
            }

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if last_state is not None:
            await self._async_restore_from_last_state(
                last_state.state, last_state.attributes
            )

        @callback
        def _listener() -> None:
            self.async_write_ha_state()

        self._runtime["listeners"].append(_listener)

        def _remove() -> None:
            listeners = self._runtime.get("listeners", [])
            if _listener in listeners:
                listeners.remove(_listener)

        self.async_on_remove(_remove)

    async def _async_restore_from_last_state(
        self, state: str, attrs: dict[str, Any]
    ) -> None:
        raise NotImplementedError


class SmartWizArtLastPushSensor(SmartWizArtBaseSensor):
    _attr_icon = "mdi:image-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_name = "Last Push"
        self._attr_unique_id = f"{self.smartwiz_device_id}_last_push"

    @property
    def native_value(self) -> datetime | None:
        return self._runtime.get("last_push_completed")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {}
        runtime = self._runtime
        last_update_meta = runtime.get("last_update_meta")
        if last_update_meta:
            attrs.update(
                {
                    "photo_preset": last_update_meta.get("photo_preset"),
                    "resolved_photo_preset": last_update_meta.get(
                        "resolved_photo_preset"
                    ),
                    "photo_avg_luma": last_update_meta.get("photo_avg_luma"),
                    "photo_contrast": last_update_meta.get("photo_contrast"),
                }
            )
        attrs.update(
            {
                "image_url": runtime.get("last_image_url"),
                "image_path": runtime.get("last_image_path"),
                "filename": runtime.get("last_output_filename"),
                "s6_filename": runtime.get(RUNTIME_LAST_S6_FILENAME),
                "last_push_completed": runtime.get("last_push_completed"),
                "last_push_started": runtime.get("last_push_started"),
                "push_state": runtime.get(RUNTIME_LAST_PUSH_STATE),
                "last_push_error": runtime.get(RUNTIME_LAST_PUSH_ERROR),
                "wake_probe_attempt": runtime.get(RUNTIME_WAKE_PROBE_ATTEMPT),
                "wake_probe_max": runtime.get(RUNTIME_WAKE_PROBE_MAX),
                "push_retry_remaining": runtime.get(RUNTIME_PUSH_RETRY_REMAINING),
                "push_retry_deadline": runtime.get(RUNTIME_PUSH_RETRY_DEADLINE),
                "push_requested_at": runtime.get(RUNTIME_PUSH_REQUESTED_AT),
            }
        )
        return attrs

    async def _async_restore_from_last_state(
        self, state: str, attrs: dict[str, Any]
    ) -> None:
        runtime = self._runtime
        if state not in ("unknown", "unavailable", ""):
            try:
                runtime["last_push_completed"] = dt_util.parse_datetime(state)
            except Exception:
                pass
        await self._async_restore_common_runtime(attrs)


class SmartWizArtPushStatusSensor(SmartWizArtBaseSensor):
    _attr_icon = "mdi:progress-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_name = "Push Status"
        self._attr_unique_id = f"{self.smartwiz_device_id}_push_status"

    @property
    def native_value(self) -> str:
        return str(self._runtime.get(RUNTIME_LAST_PUSH_STATE) or PUSH_STATE_IDLE)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self._runtime
        return {
            "wake_probe_attempt": runtime.get(RUNTIME_WAKE_PROBE_ATTEMPT),
            "wake_probe_max": runtime.get(RUNTIME_WAKE_PROBE_MAX),
            "push_retry_remaining": runtime.get(RUNTIME_PUSH_RETRY_REMAINING),
            "push_retry_remaining_seconds": runtime.get(
                RUNTIME_PUSH_RETRY_REMAINING_SECONDS
            ),
            "push_retry_deadline": runtime.get(RUNTIME_PUSH_RETRY_DEADLINE),
            "push_requested_at": runtime.get(RUNTIME_PUSH_REQUESTED_AT),
            "s6_filename": runtime.get(RUNTIME_LAST_S6_FILENAME),
            "last_push_error": runtime.get(RUNTIME_LAST_PUSH_ERROR),
            "last_push_started": runtime.get("last_push_started"),
            "last_push_completed": runtime.get("last_push_completed"),
            "push_loop_active": runtime.get(RUNTIME_PUSH_LOOP_ACTIVE, False),
        }

    @property
    def icon(self) -> str:
        state = self.native_value
        active = self._runtime.get(RUNTIME_PUSH_LOOP_ACTIVE, False)

        # 動作中は回転系アイコン優先
        if active:
            return "mdi:autorenew"

        return {
            PUSH_STATE_IDLE: "mdi:sleep",
            PUSH_STATE_WAITING: "mdi:wifi-search",
            "warming_up": "mdi:timer-sand",
            PUSH_STATE_PUSHING: "mdi:upload",
            PUSH_STATE_SUCCESS: "mdi:check-circle",
            PUSH_STATE_FAILED: "mdi:alert-circle",
            PUSH_STATE_EXPIRED: "mdi:timer-off",
        }.get(state, "mdi:help-circle")

    async def _async_restore_from_last_state(
        self, state: str, attrs: dict[str, Any]
    ) -> None:
        runtime = self._runtime
        if state not in ("unknown", "unavailable", ""):
            runtime[RUNTIME_LAST_PUSH_STATE] = state
        await self._async_restore_common_runtime(attrs)
