from __future__ import annotations

import traceback
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_der_private_key

from ..const import get_device_key_dir, get_device_state_dir
from ..util import epd_util


class SmartWizArtDisplayError(RuntimeError):
    pass


def _resolve_key_paths(device_id: str) -> tuple[Path, Path]:
    key_dir = get_device_key_dir(device_id)

    private_key_path = key_dir / "app_private.der"
    epd_public_key_file_path = key_dir / "epd_public_key.der"

    if not key_dir.exists():
        raise SmartWizArtDisplayError(
            f"SMARTWIZ+ art key directory not found: {key_dir}"
        )

    if not private_key_path.exists():
        raise SmartWizArtDisplayError(
            f"SMARTWIZ+ art private key not found: {private_key_path}"
        )

    if not epd_public_key_file_path.exists():
        raise SmartWizArtDisplayError(
            f"SMARTWIZ+ art public key not found: {epd_public_key_file_path}"
        )

    return private_key_path, epd_public_key_file_path


def _ensure_state_dir(device_id: str) -> Path:
    state_dir = get_device_state_dir(device_id)
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def push_local_image(
    *,
    device_id: str,
    s6_image_file_path: str | Path,
    api_url: str | None = None,
    caption: str = "SMARTWIZ+ art",
    orientation: int = 0,
    x_offset: int = 0,
    y_offset: int = 0,
    width: int = 800,
    height: int = 480,
    user_name: str = "smartwizart-ha-user",
    user_comment: str = "user image by smartwizart-ha",
) -> dict:
    s6_image_file_path = Path(s6_image_file_path)

    if not s6_image_file_path.exists():
        raise SmartWizArtDisplayError(f"s6 file not found: {s6_image_file_path}")

    private_key_path, epd_public_key_file_path = _resolve_key_paths(device_id)

    if api_url is None:
        api_url = f"http://smartwiz-art-{device_id}.local/api/control/request"

    with open(private_key_path, "rb") as f:
        app_private_key = load_der_private_key(f.read(), password=None)

    with open(epd_public_key_file_path, "rb") as f:
        epd_public_key_bin = f.read()

    epd_public_key = serialization.load_der_public_key(epd_public_key_bin)

    cbc_iv = device_id[16:].encode("ascii")

    state_dir = _ensure_state_dir(device_id)
    request_id_file = state_dir / "request_id.txt"
    image_id_file = state_dir / "image_id.txt"

    if not request_id_file.exists():
        epd_util.initialize_request_id_file(state_dir, 0)

    if not image_id_file.exists():
        epd_util.initialize_image_id_file(state_dir, 0)

    request_id = epd_util.get_request_id(True, state_dir)
    request_utc = epd_util.get_current_request_utc()

    encrypted_image = epd_util.make_encrypted_image(
        0,
        str(s6_image_file_path),
        epd_public_key,
        cbc_iv,
        x_offset,
        y_offset,
        width,
        height,
        caption,
        orientation,
    )

    response = epd_util.send_image_upload_request(
        api_url,
        request_id,
        request_utc,
        app_private_key,
        encrypted_image,
    )
    if response is None:
        raise SmartWizArtDisplayError("image upload request returned no response")

    json_resp = response.json()
    if "file" not in json_resp:
        raise SmartWizArtDisplayError(f"upload response missing file: {json_resp}")

    file_id = json_resp["file"]

    request_id = epd_util.get_request_id(True, state_dir)
    request_utc = epd_util.get_current_request_utc()

    response = epd_util.send_display_request(
        api_url,
        request_id,
        request_utc,
        app_private_key,
        file_id,
        user_name,
        user_comment,
    )
    if response is None:
        raise SmartWizArtDisplayError("display request returned no response")

    display_resp = response.json()
    return {
        "upload": json_resp,
        "display": display_resp,
    }


def main() -> int:
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 display_local_image.py <device_id> <image_file.s6>")
        return 1

    try:
        result = push_local_image(
            device_id=sys.argv[1],
            s6_image_file_path=sys.argv[2],
        )
        print(result)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
