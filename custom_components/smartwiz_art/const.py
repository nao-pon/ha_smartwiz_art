from __future__ import annotations

from datetime import timedelta
from pathlib import Path

DOMAIN = "smartwiz_art"

SERVICE_RENDER_TODAY = "render_today"
SERVICE_UPDATE = "update"
SERVICE_PUSH_FILE = "push_file"
SERVICE_UPDATE_AND_PUSH = "update_and_push"
SERVICE_REGISTER_DEVICE = "register_device"
SERVICE_UNREGISTER_DEVICE = "unregister_device"

DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 480

INTEGRATION_DIR = "/config/custom_components/smartwiz_art"
VENDOR_DIR = f"{INTEGRATION_DIR}/vendor"

SMARTWIZ_ART_CONFIG_BASE = "/config/.smartwiz_art"

DEFAULT_OUTPUT_DIR = "/config/www/smartwiz_art"

DEFAULT_FILENAME = "today.png"
DEFAULT_TEMPLATE = "today"
DEFAULT_THEME = "washi"


PUSH_STATE_IDLE = "idle"
PUSH_STATE_WAITING = "waiting"
PUSH_STATE_PUSHING = "pushing"
PUSH_STATE_SUCCESS = "success"
PUSH_STATE_FAILED = "failed"
PUSH_STATE_EXPIRED = "expired"

RUNTIME_LAST_PUSH_STATE = "last_push_state"
RUNTIME_LAST_PUSH_ERROR = "last_push_error"
RUNTIME_LAST_S6_FILENAME = "last_s6_filename"
RUNTIME_PUSH_LOOP_ACTIVE = "push_loop_active"

RUNTIME_WAKE_PROBE_ATTEMPT = "wake_probe_attempt"
RUNTIME_WAKE_PROBE_MAX = "wake_probe_max"
RUNTIME_PUSH_RETRY_REMAINING = "push_retry_remaining"
RUNTIME_PUSH_RETRY_REMAINING_SECONDS = "push_retry_remaining_seconds"
RUNTIME_PUSH_RETRY_DEADLINE = "push_retry_deadline"
RUNTIME_PUSH_REQUESTED_AT = "push_requested_at"

MAX_PUSH_RETRY_HOURS = 12
MAX_PUSH_RETRY_AGE = timedelta(hours=MAX_PUSH_RETRY_HOURS)

PENDING_PUSH_STORE_VERSION = 1
PENDING_PUSH_STORE_KEY = f"{DOMAIN}_pending_pushes"


def _normalize_device_id(device_id: str) -> str:
    value = str(device_id or "").strip()
    if not value:
        raise ValueError("device_id is required")
    return value.replace("/", "_")


def get_device_base_dir(device_id: str) -> Path:
    return Path(SMARTWIZ_ART_CONFIG_BASE) / _normalize_device_id(device_id)


def get_device_key_dir(device_id: str) -> Path:
    return get_device_base_dir(device_id) / "keys"


def get_device_state_dir(device_id: str) -> Path:
    return get_device_base_dir(device_id) / "state"


def get_device_cache_dir(device_id: str) -> Path:
    return get_device_base_dir(device_id) / "cache"
