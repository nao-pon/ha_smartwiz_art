from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    MAX_PUSH_RETRY_AGE,
    MAX_PUSH_RETRY_HOURS,
    PENDING_PUSH_STORE_KEY,
    PENDING_PUSH_STORE_VERSION,
    PUSH_STATE_WAITING,
    get_device_cache_dir,
)
from .image.converter import convert_png_to_s6
from .transport.transport import SmartWizArtTransportError, ping_host, push_s6_file

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PushRuntimeHooks:
    """PushManager から runtime 更新を行うためのフック群。"""

    set_push_loop_active: Callable[[HomeAssistant, ConfigEntry | None, bool], None]
    notify_runtime_updated: Callable[[HomeAssistant, ConfigEntry | None], None]
    get_runtime: Callable[[HomeAssistant, ConfigEntry | None], dict | None]
    set_push_started: Callable[[HomeAssistant, ConfigEntry | None, str], None]
    set_pushing: Callable[[HomeAssistant, ConfigEntry | None, str], None]
    set_push_completed: Callable[[HomeAssistant, ConfigEntry | None, str], None]
    set_push_failed: Callable[[HomeAssistant, ConfigEntry | None, str, str], None]
    set_push_expired: Callable[[HomeAssistant, ConfigEntry | None, str, str], None]
    clear_retry_runtime: Callable[[HomeAssistant, ConfigEntry | None], None]
    update_retry_runtime: Callable[[HomeAssistant, ConfigEntry | None], Awaitable[None]]


class PushManager:
    """SMARTWIZ+ art の push/retry/pending を管理する。"""

    def __init__(
        self,
        hass: HomeAssistant,
        hooks: PushRuntimeHooks,
    ) -> None:
        self.hass = hass
        self.hooks = hooks
        self._store = Store[dict[str, Any]](
            hass,
            PENDING_PUSH_STORE_VERSION,
            PENDING_PUSH_STORE_KEY,
        )
        self._active_tasks: dict[str, asyncio.Task] = {}

    # -------------------------------------------------------------------------
    # public
    # -------------------------------------------------------------------------

    async def convert_png_to_s6(
        self, input_path: Path, s6_path: Path, convert_options: dict | None = None
    ) -> None:
        convert_options = dict(convert_options or {})
        await self.hass.async_add_executor_job(
            partial(
                convert_png_to_s6,
                input_path=input_path,
                output_path=s6_path,
                convert_options=convert_options,
            )
        )

    async def restore_pending_pushes(self, entry: ConfigEntry) -> None:
        if self.is_push_loop_active(entry):
            _LOGGER.debug(
                "SMARTWIZ+ art restore skipped because push loop is already active: entry_id=%s",
                entry.entry_id,
            )
            return

        data = await self._load_pending_pushes()
        pending = data.get(entry.entry_id)
        if not isinstance(pending, dict):
            return

        if await self.is_pending_push_expired(entry):
            _LOGGER.debug(
                "SMARTWIZ+ art pending push expired on startup: entry_id=%s",
                entry.entry_id,
            )
            runtime = self.hooks.get_runtime(self.hass, entry)
            if runtime is not None:
                runtime["last_push_state"] = "expired"
                runtime["last_push_error"] = (
                    f"Push retry expired after {MAX_PUSH_RETRY_HOURS}h on startup"
                )
                self.hooks.clear_retry_runtime(self.hass, entry)
                self.hooks.notify_runtime_updated(self.hass, entry)

            data.pop(entry.entry_id, None)
            await self._save_pending_pushes(data)
            return

        s6_filename = str(pending.get("s6_filename") or "")
        if not s6_filename:
            return

        device_id = str(entry.data.get("device_id") or "")
        host = str(entry.data.get("host") or "")
        if not device_id:
            data.pop(entry.entry_id, None)
            await self._save_pending_pushes(data)
            return

        s6_path = get_device_cache_dir(device_id) / s6_filename
        if not s6_path.exists():
            data.pop(entry.entry_id, None)
            await self._save_pending_pushes(data)
            return

        runtime = self.hooks.get_runtime(self.hass, entry)
        if runtime is not None:
            runtime["last_push_state"] = PUSH_STATE_WAITING
            runtime["last_push_error"] = None
            runtime["last_s6_filename"] = s6_filename
            await self.hooks.update_retry_runtime(self.hass, entry)
            self.hooks.notify_runtime_updated(self.hass, entry)

        _LOGGER.debug(
            "SMARTWIZ+ art restoring pending push from startup: entry_id=%s, s6=%s",
            entry.entry_id,
            s6_filename,
        )

        started = self.start_push_task(
            entry=entry,
            host=host,
            device_id=device_id,
            s6_filename=s6_filename,
        )
        if not started:
            _LOGGER.debug(
                "SMARTWIZ+ art restore skipped because push loop is already active: entry_id=%s, s6=%s",
                entry.entry_id,
                s6_filename,
            )

    async def enqueue_push(
        self,
        entry: ConfigEntry,
        host: str,
        device_id: str,
        s6_filename: str,
    ) -> bool:
        """
        pending を更新し、push ループが止まっていれば開始する。
        動作中なら pending だけ差し替えて既存ループに最新 s6 を使わせる。
        """
        await self.set_pending_push(entry, s6_filename)

        if self.is_push_loop_active(entry):
            runtime = self.hooks.get_runtime(self.hass, entry)
            if runtime is not None:
                runtime["last_s6_filename"] = s6_filename
                self.hooks.notify_runtime_updated(self.hass, entry)

            _LOGGER.debug(
                "SMARTWIZ+ art push loop already active, updated pending s6 only: entry_id=%s, s6=%s",
                entry.entry_id,
                s6_filename,
            )
            return False

        return self.start_push_task(
            entry=entry,
            host=host,
            device_id=device_id,
            s6_filename=s6_filename,
        )

    def start_push_task(
        self,
        entry: ConfigEntry,
        host: str,
        device_id: str,
        s6_filename: str,
    ) -> bool:
        task = self._active_tasks.get(entry.entry_id)
        if task is not None and not task.done():
            return False

        task = self.hass.async_create_task(
            self._run_push_task(
                entry=entry,
                host=host,
                device_id=device_id,
                s6_filename=s6_filename,
            )
        )
        self._active_tasks[entry.entry_id] = task

        def _done_callback(_task: asyncio.Task) -> None:
            current = self._active_tasks.get(entry.entry_id)
            if current is _task:
                self._active_tasks.pop(entry.entry_id, None)

        task.add_done_callback(_done_callback)
        return True

    def get_active_task(self, entry: ConfigEntry) -> asyncio.Task | None:
        task = self._active_tasks.get(entry.entry_id)
        if task is not None and task.done():
            self._active_tasks.pop(entry.entry_id, None)
            return None
        return task

    async def cancel_push(self, entry: ConfigEntry) -> None:
        task = self.get_active_task(entry)
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._active_tasks.pop(entry.entry_id, None)
            self.hooks.set_push_loop_active(self.hass, entry, False)

    def is_push_loop_active(self, entry: ConfigEntry | None) -> bool:
        if entry is None:
            return False
        runtime = self.hooks.get_runtime(self.hass, entry)
        if not runtime:
            return False
        return bool(runtime.get("push_loop_active", False))

    # -------------------------------------------------------------------------
    # pending store
    # -------------------------------------------------------------------------

    async def _load_pending_pushes(self) -> dict[str, dict[str, Any]]:
        data = await self._store.async_load()
        if isinstance(data, dict):
            return data
        return {}

    async def _save_pending_pushes(self, data: dict[str, dict[str, Any]]) -> None:
        await self._store.async_save(data)

    async def set_pending_push(self, entry: ConfigEntry, s6_filename: str) -> None:
        data = await self._load_pending_pushes()
        data[entry.entry_id] = {
            "entry_id": entry.entry_id,
            "s6_filename": s6_filename,
            "requested_at": dt_util.now().isoformat(),
        }
        await self._save_pending_pushes(data)

    async def clear_pending_push(self, entry: ConfigEntry) -> None:
        data = await self._load_pending_pushes()
        if entry.entry_id in data:
            data.pop(entry.entry_id, None)
            await self._save_pending_pushes(data)

    async def get_pending_s6_filename(self, entry: ConfigEntry) -> str | None:
        data = await self._load_pending_pushes()
        pending = data.get(entry.entry_id)
        if not isinstance(pending, dict):
            return None
        s6_filename = pending.get("s6_filename")
        return str(s6_filename) if s6_filename else None

    async def is_pending_push_expired(self, entry: ConfigEntry) -> bool:
        data = await self._load_pending_pushes()
        pending = data.get(entry.entry_id)
        if not isinstance(pending, dict):
            return False

        requested_at = pending.get("requested_at")
        if not requested_at:
            return False

        try:
            requested_dt = dt_util.parse_datetime(requested_at)
        except Exception:
            return False

        if requested_dt is None:
            return False

        now = dt_util.utcnow()
        return (now - requested_dt) > MAX_PUSH_RETRY_AGE

    # -------------------------------------------------------------------------
    # push loop
    # -------------------------------------------------------------------------

    async def _run_push_task(
        self,
        entry: ConfigEntry,
        host: str,
        device_id: str,
        s6_filename: str,
    ) -> None:
        self.hooks.set_push_loop_active(self.hass, entry, True)
        try:
            await self._push_s6_with_retry(
                entry=entry,
                host=host,
                device_id=device_id,
                s6_filename=s6_filename,
            )
        except asyncio.CancelledError:
            _LOGGER.debug(
                "SMARTWIZ+ art push task cancelled: entry_id=%s",
                entry.entry_id,
            )
            raise
        finally:
            self.hooks.set_push_loop_active(self.hass, entry, False)

    async def _push_s6_with_retry(
        self,
        entry: ConfigEntry,
        host: str,
        device_id: str,
        s6_filename: str,
        probe_interval: int = 20,
        max_probe_count: int = 210,
    ) -> None:

        warmup_delay = 5
        burst_delays = [0, 10, 15, 15]
        ping_count = 3
        ping_timeout = 1

        async def _resolve_current_s6() -> tuple[str, Path]:
            latest_s6_filename = (
                await self.get_pending_s6_filename(entry) or s6_filename
            )
            latest_s6_path = get_device_cache_dir(device_id) / latest_s6_filename
            return latest_s6_filename, latest_s6_path

        async def _burst_push() -> bool:
            current_s6_filename, current_s6_path = await _resolve_current_s6()
            self.hooks.set_push_started(self.hass, entry, current_s6_filename)

            for i, delay in enumerate(burst_delays, start=1):
                if delay > 0:
                    await self._sleep(delay)

                current_s6_filename, current_s6_path = await _resolve_current_s6()
                self.hooks.set_pushing(self.hass, entry, current_s6_filename)

                try:
                    _LOGGER.debug(
                        "SMARTWIZ+ art push attempt (burst %s/%s): %s",
                        i,
                        len(burst_delays),
                        current_s6_path,
                    )
                    await self.hass.async_add_executor_job(
                        push_s6_file,
                        device_id,
                        current_s6_path,
                        host,
                    )
                    _LOGGER.debug(
                        "SMARTWIZ+ art push succeeded on burst attempt %s/%s: %s",
                        i,
                        len(burst_delays),
                        current_s6_path,
                    )
                    self.hooks.set_push_completed(self.hass, entry, current_s6_filename)
                    await self.clear_pending_push(entry)
                    return True

                except SmartWizArtTransportError as err:
                    _LOGGER.warning(
                        "SMARTWIZ+ art burst push failed on attempt %s/%s for %s: %s",
                        i,
                        len(burst_delays),
                        current_s6_path,
                        err,
                    )

                except Exception as err:
                    _LOGGER.exception(
                        "SMARTWIZ+ art unexpected burst push error on attempt %s/%s for %s: %s",
                        i,
                        len(burst_delays),
                        current_s6_path,
                        err,
                    )

            return False

        async def _probe_loop(attempt_no: int) -> None:
            if await self.is_pending_push_expired(entry):
                latest_s6_filename, latest_s6_path = await _resolve_current_s6()
                msg = f"Push retry expired after {MAX_PUSH_RETRY_HOURS}h: {latest_s6_path}"
                _LOGGER.warning("SMARTWIZ+ art %s", msg)
                self.hooks.set_push_expired(
                    self.hass,
                    entry,
                    msg,
                    latest_s6_filename,
                )
                await self.clear_pending_push(entry)
                return

            reset_probe_counter = False
            current_s6_filename, current_s6_path = await _resolve_current_s6()

            runtime = self.hooks.get_runtime(self.hass, entry)
            if runtime:
                runtime["last_push_state"] = PUSH_STATE_WAITING
                runtime["last_push_error"] = None
                runtime["last_s6_filename"] = current_s6_filename
                await self.hooks.update_retry_runtime(self.hass, entry)
                self.hooks.notify_runtime_updated(self.hass, entry)

            _LOGGER.debug(
                "SMARTWIZ+ art probe attempt %s/%s: host=%s, s6=%s",
                attempt_no,
                max_probe_count,
                host,
                current_s6_filename,
            )

            reachable = False
            if host:
                try:
                    reachable = await self.hass.async_add_executor_job(
                        ping_host,
                        host,
                        ping_timeout,
                        ping_count,
                    )
                except Exception as err:
                    _LOGGER.exception(
                        "SMARTWIZ+ art ping error on probe %s/%s for host %s: %s",
                        attempt_no,
                        max_probe_count,
                        host,
                        err,
                    )

            if reachable:
                _LOGGER.debug(
                    "SMARTWIZ+ art host responded to ping on probe %s/%s: %s",
                    attempt_no,
                    max_probe_count,
                    host,
                )

                if warmup_delay > 0:
                    _LOGGER.debug(
                        "SMARTWIZ+ art warmup wait %ss after ping success: %s",
                        warmup_delay,
                        host,
                    )
                    await self._sleep(warmup_delay)

                success = await _burst_push()
                if success:
                    return

                latest_s6_filename, latest_s6_path = await _resolve_current_s6()
                msg = f"Burst push exhausted after ping success: {latest_s6_path}"
                _LOGGER.warning("SMARTWIZ+ art %s", msg)
                self.hooks.set_push_failed(
                    self.hass,
                    entry,
                    msg,
                    latest_s6_filename,
                )
                reset_probe_counter = True
            else:
                _LOGGER.debug(
                    "SMARTWIZ+ art host did not respond to ping on probe %s/%s: %s",
                    attempt_no,
                    max_probe_count,
                    host,
                )

            if attempt_no >= max_probe_count:
                latest_s6_filename, latest_s6_path = await _resolve_current_s6()
                msg = f"Push exhausted probe window without success: {latest_s6_path}"
                _LOGGER.error("SMARTWIZ+ art %s", msg)
                self.hooks.set_push_failed(
                    self.hass,
                    entry,
                    msg,
                    latest_s6_filename,
                )
                await self.clear_pending_push(entry)
                return

            _LOGGER.debug(
                "SMARTWIZ+ art scheduling next probe in %ss: entry_id=%s",
                probe_interval,
                entry.entry_id,
            )

            wait_seconds = max(1, probe_interval - (ping_timeout * ping_count))
            await self._sleep(wait_seconds)

            next_attempt_no = 1 if reset_probe_counter else (attempt_no + 1)
            await _probe_loop(next_attempt_no)

        await _probe_loop(1)

    # -------------------------------------------------------------------------
    # small utils
    # -------------------------------------------------------------------------

    async def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return

        future = self.hass.loop.create_future()

        @callback
        def _resume(_now) -> None:
            if not future.done():
                future.set_result(True)

        async_call_later(self.hass, seconds, _resume)
        await future
