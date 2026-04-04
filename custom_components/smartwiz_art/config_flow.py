from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DEFAULT_HEIGHT, DEFAULT_WIDTH, DOMAIN
from .core.register import (
    SmartWizArtKeyExchangeError,
    SmartWizArtRegistrationConnectionError,
    SmartWizArtRegistrationError,
    SmartWizArtRegistrationTimeoutError,
    register_device_sync,
)

DISCOVERY_CONFIRM_SCHEMA = vol.Schema({})
HOSTNAME_DEVICE_ID_RE = re.compile(r"^smartwiz-art-([^.]+)\.local$", re.IGNORECASE)


def _build_user_schema(
    *,
    device_id: str = "",
    host: str = "",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("device_id", default=device_id): str,
            vol.Optional("host", default=host): str,
            vol.Optional("width", default=width): int,
            vol.Optional("height", default=height): int,
        }
    )


def _build_reconfigure_schema(
    *,
    host: str = "",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional("host", default=host): str,
            vol.Optional("width", default=width): int,
            vol.Optional("height", default=height): int,
        }
    )


def _normalize_device_id(device_id: str | None) -> str:
    value = str(device_id or "").strip()
    if not value:
        raise ValueError("device_id is required")
    return value


def _normalize_host(device_id: str, host: str | None) -> str:
    host_value = str(host or "").strip()
    if host_value:
        return host_value
    return f"smartwiz-art-{device_id}.local"


def _extract_device_id_from_hostname(hostname: str | None) -> str | None:
    value = str(hostname or "").strip().rstrip(".").lower()
    match = HOSTNAME_DEVICE_ID_RE.match(value)
    if not match:
        return None
    return match.group(1)


def _map_registration_error(exc: Exception) -> str:
    if isinstance(exc, SmartWizArtRegistrationTimeoutError):
        return "registration_timeout"
    if isinstance(exc, SmartWizArtKeyExchangeError):
        return "key_exchange_failed"
    if isinstance(exc, SmartWizArtRegistrationConnectionError):
        return "cannot_connect"
    if isinstance(exc, SmartWizArtRegistrationError):
        return "cannot_register"
    return "unknown"


class SmartWizArtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SMARTWIZ+ art."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                device_id = _normalize_device_id(user_input.get("device_id"))
                host = _normalize_host(device_id, user_input.get("host"))

                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured(updates={"host": host})

                await self.hass.async_add_executor_job(
                    register_device_sync,
                    device_id,
                    host,
                )
            except ValueError:
                errors["base"] = "invalid_device_id"
            except (SmartWizArtRegistrationError, Exception) as exc:
                errors["base"] = _map_registration_error(exc)
            else:
                data = dict(user_input)
                data["device_id"] = device_id
                data["host"] = host
                return self.async_create_entry(
                    title=f"SMARTWIZ+ art ({device_id})",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                device_id = _normalize_device_id(entry.data.get("device_id"))
                host = _normalize_host(device_id, user_input.get("host"))
            except ValueError:
                errors["base"] = "invalid_device_id"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_mismatch()

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        "host": host,
                        "width": user_input.get(
                            "width", entry.data.get("width", DEFAULT_WIDTH)
                        ),
                        "height": user_input.get(
                            "height", entry.data.get("height", DEFAULT_HEIGHT)
                        ),
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_reconfigure_schema(
                host=entry.data.get("host", ""),
                width=entry.data.get("width", DEFAULT_WIDTH),
                height=entry.data.get("height", DEFAULT_HEIGHT),
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        hostname = str(getattr(discovery_info, "hostname", "") or "")
        device_id = _extract_device_id_from_hostname(hostname)
        if not device_id:
            return self.async_abort(reason="not_smartwiz_art")

        host = str(getattr(discovery_info, "host", "") or "").strip()
        if not host:
            return self.async_abort(reason="cannot_resolve")

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={"host": host})

        self.context["title_placeholders"] = {
            "name": f"SMARTWIZ+ art ({device_id})",
        }
        self._discovered_data = {
            "device_id": device_id,
            "host": host,
            "width": DEFAULT_WIDTH,
            "height": DEFAULT_HEIGHT,
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery before creating the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    register_device_sync,
                    self._discovered_data["device_id"],
                    self._discovered_data["host"],
                )
            except SmartWizArtRegistrationError as exc:
                errors["base"] = _map_registration_error(exc)
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"SMARTWIZ+ art ({self._discovered_data['device_id']})",
                    data=dict(self._discovered_data),
                )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=DISCOVERY_CONFIRM_SCHEMA,
            description_placeholders={
                "device_id": self._discovered_data.get("device_id", ""),
                "host": self._discovered_data.get("host", ""),
            },
            errors=errors,
        )
