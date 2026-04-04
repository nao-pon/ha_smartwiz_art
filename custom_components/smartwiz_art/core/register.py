from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

from ..const import get_device_key_dir, get_device_state_dir
from ..util.crypto import (
    ensure_app_keypair,
    has_app_private_key,
    has_epd_public_key,
    load_app_private_key,
    load_app_public_key_der,
    save_epd_public_key,
)
from ..util.epd_util import (
    SmartWizArtRequestConnectionError,
    SmartWizArtRequestError,
    SmartWizArtRequestTimeoutError,
    get_request_id,
    initialize_request_id_file,
    send_device_register_request,
    send_device_unregister_request,
)


class SmartWizArtRegistrationError(RuntimeError):
    """Raised when register/unregister failed in a recoverable way."""


class SmartWizArtRegistrationTimeoutError(SmartWizArtRegistrationError):
    """Raised when the device does not respond in time."""


class SmartWizArtKeyExchangeError(SmartWizArtRegistrationError):
    """Raised when the device responds but key registration fails."""


class SmartWizArtRegistrationConnectionError(SmartWizArtRegistrationError):
    """Raised when the device cannot be reached over the network."""


def _api_url(host: str) -> str:
    host_value = str(host or "").strip()
    if not host_value:
        raise ValueError("host is required")
    return f"http://{host_value}/api/control/request"


def _current_request_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_request_id_state(device_id: str, initial_value: int = 1) -> Path:
    state_dir = get_device_state_dir(device_id)
    state_dir.mkdir(parents=True, exist_ok=True)

    request_id_file = state_dir / "request_id.txt"
    if not request_id_file.exists():
        initialize_request_id_file(state_dir, initial_value)

    return state_dir


def register_device_sync(device_id: str, host: str) -> dict:
    ensure_app_keypair(device_id)
    request_id_path = _ensure_request_id_state(device_id)

    try:
        response = send_device_register_request(
            _api_url(host),
            get_request_id(True, request_id_path),
            _current_request_utc(),
            load_app_private_key(device_id),
            load_app_public_key_der(device_id),
        )
    except SmartWizArtRequestTimeoutError as exc:
        raise SmartWizArtRegistrationTimeoutError(
            "device_register_request timed out"
        ) from exc
    except SmartWizArtRequestConnectionError as exc:
        raise SmartWizArtRegistrationConnectionError(
            "device_register_request could not reach the device"
        ) from exc
    except SmartWizArtRequestError as exc:
        raise SmartWizArtRegistrationError(
            f"device_register_request transport error: {exc}"
        ) from exc

    try:
        payload = response.json()
    except Exception as exc:
        raise SmartWizArtKeyExchangeError(
            f"device_register_request returned invalid JSON: HTTP {response.status_code}, body={response.text!r}"
        ) from exc

    if response.status_code >= 400:
        raise SmartWizArtKeyExchangeError(
            f"device_register_request failed: HTTP {response.status_code}, payload={payload}"
        )

    if payload.get("result") is True and "public_key" in payload:
        epd_public_key_der = base64.b64decode(payload["public_key"])
        save_epd_public_key(device_id, epd_public_key_der)
        return {
            "ok": True,
            "status": "registered",
            "payload": payload,
        }

    if payload.get("msg") == "Device already registered":
        if has_epd_public_key(device_id):
            return {
                "ok": True,
                "status": "already_registered",
                "reused_existing_keys": True,
                "payload": payload,
            }

        if has_app_private_key(device_id):
            raise SmartWizArtKeyExchangeError(
                "Device already registered, but local epd_public_key.der is missing. "
                "Unregister the device and register it again, or reset the device by holding the button for 10 seconds."
            )

        raise SmartWizArtKeyExchangeError(
            "Device already registered, but local registration keys are missing. "
            "Reset the device by holding the button for 10 seconds, reconfigure Wi-Fi over Bluetooth, and register again."
        )

    raise SmartWizArtKeyExchangeError(
        f"device_register_request failed: payload={payload}"
    )


def unregister_device_sync(
    device_id: str, host: str, *, purge_local_keys: bool = False
) -> dict:
    private_key_path = get_device_key_dir(device_id) / "app_private.der"
    if not private_key_path.exists():
        raise SmartWizArtRegistrationError(
            "Cannot unregister because app_private.der is missing. "
            "If the key has been lost, reset the device by holding the button for 10 seconds."
        )

    request_id_path = _ensure_request_id_state(device_id)

    try:
        response = send_device_unregister_request(
            _api_url(host),
            get_request_id(True, request_id_path),
            _current_request_utc(),
            load_app_private_key(device_id),
        )
    except SmartWizArtRequestTimeoutError as exc:
        raise SmartWizArtRegistrationTimeoutError(
            "device_unregister_request timed out"
        ) from exc
    except SmartWizArtRequestConnectionError as exc:
        raise SmartWizArtRegistrationConnectionError(
            "device_unregister_request could not reach the device"
        ) from exc
    except SmartWizArtRequestError as exc:
        raise SmartWizArtRegistrationError(
            f"device_unregister_request transport error: {exc}"
        ) from exc

    try:
        payload = response.json()
    except Exception as exc:
        raise SmartWizArtRegistrationError(
            f"device_unregister_request returned invalid JSON: HTTP {response.status_code}, body={response.text!r}"
        ) from exc

    if response.status_code >= 400:
        raise SmartWizArtRegistrationError(
            f"device_unregister_request failed: HTTP {response.status_code}, payload={payload}"
        )

    if payload.get("result") is True:
        key_dir = get_device_key_dir(device_id)
        epd_public_key_path = key_dir / "epd_public_key.der"
        if epd_public_key_path.exists():
            epd_public_key_path.unlink()

        if purge_local_keys:
            for name in ("app_private.der", "app_public.der"):
                path = key_dir / name
                if path.exists():
                    path.unlink()

        return {
            "ok": True,
            "status": "unregistered",
            "purge_local_keys": purge_local_keys,
            "payload": payload,
        }

    raise SmartWizArtRegistrationError(
        f"device_unregister_request failed: payload={payload}"
    )
