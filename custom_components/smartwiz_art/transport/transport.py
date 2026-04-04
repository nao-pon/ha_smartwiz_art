from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from ..image.display_local_image import SmartWizArtDisplayError, push_local_image


class SmartWizArtTransportError(RuntimeError):
    """Raised when pushing an image fails."""


def ping_host(host: str, timeout_seconds: int = 1, count: int = 3) -> bool:
    """Return True if host responds to ping."""
    if not host:
        return False

    system = platform.system().lower()

    if system == "windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout_seconds * 1000), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout_seconds), host]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def push_s6_file(device_id: str, s6_path: str | Path, host: str | None = None) -> dict:
    s6_path = Path(s6_path)

    if not device_id:
        raise SmartWizArtTransportError("device_id is required")

    if not s6_path.exists():
        raise SmartWizArtTransportError(f"S6 file not found: {s6_path}")

    try:
        return push_local_image(
            device_id=device_id,
            s6_image_file_path=s6_path,
            api_url=f"http://{host}/api/control/request" if host else None,
        )
    except SmartWizArtDisplayError as err:
        raise SmartWizArtTransportError(str(err)) from err
    except Exception as err:
        raise SmartWizArtTransportError(f"Unexpected push error: {err}") from err
