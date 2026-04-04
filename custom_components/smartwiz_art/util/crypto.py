from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..const import get_device_key_dir


def ensure_app_keypair(device_id: str) -> tuple[Path, Path]:
    key_dir = get_device_key_dir(device_id)
    key_dir.mkdir(parents=True, exist_ok=True)

    private_path = key_dir / "app_private.der"
    public_path = key_dir / "app_public.der"

    if private_path.exists() and public_path.exists():
        return private_path, public_path

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_bytes)
    public_path.write_bytes(public_bytes)
    return private_path, public_path


def load_app_private_key(device_id: str):
    private_path = get_device_key_dir(device_id) / "app_private.der"
    return serialization.load_der_private_key(private_path.read_bytes(), password=None)


def load_app_public_key_der(device_id: str) -> bytes:
    return (get_device_key_dir(device_id) / "app_public.der").read_bytes()


def save_epd_public_key(device_id: str, der_bytes: bytes) -> Path:
    key_dir = get_device_key_dir(device_id)
    key_dir.mkdir(parents=True, exist_ok=True)
    epd_public_key_path = key_dir / "epd_public_key.der"
    epd_public_key_path.write_bytes(der_bytes)
    return epd_public_key_path


def has_app_private_key(device_id: str) -> bool:
    return (get_device_key_dir(device_id) / "app_private.der").exists()


def has_epd_public_key(device_id: str) -> bool:
    return (get_device_key_dir(device_id) / "epd_public_key.der").exists()


def has_registration_keys(device_id: str) -> bool:
    return has_app_private_key(device_id) and has_epd_public_key(device_id)
