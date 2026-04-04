from __future__ import annotations

from pathlib import Path

from .convert_image import convert_image_file


class SmartWizArtConvertError(RuntimeError):
    """Raised when image conversion fails."""


def convert_png_to_s6(
    input_path: str | Path,
    output_path: str | Path,
    target_width: int = 800,
    target_height: int = 480,
    auto_rotate_portrait: bool = True,
    convert_options: dict | None = None
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise SmartWizArtConvertError(f"Input file not found: {input_path}")

    try:
        return convert_image_file(
            input_path,
            output_path,
            target_width=target_width,
            target_height=target_height,
            auto_rotate_portrait=auto_rotate_portrait,
            convert_options=convert_options,
        )
    except Exception as err:
        raise SmartWizArtConvertError(str(err)) from err
