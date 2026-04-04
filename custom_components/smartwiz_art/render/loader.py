from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from typing import Any

from PIL import Image

_LOGGER = logging.getLogger(__name__)

RenderFunc = Callable[[Any, Any], Image.Image]


def _iter_template_modules():
    package_name = __package__  # custom_components.smartwiz_art.render
    package = importlib.import_module(package_name)

    for module_info in pkgutil.iter_modules(package.__path__):
        module_name = module_info.name
        if not module_name.startswith("template_"):
            continue

        try:
            yield importlib.import_module(f".{module_name}", package_name)
        except Exception:
            _LOGGER.exception("Failed to import template module: %s", module_name)


def load_template_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    for module in _iter_template_modules():
        templates = getattr(module, "TEMPLATES", None)
        render_func = getattr(module, "render", None)

        if not isinstance(templates, dict):
            _LOGGER.warning("Template module %s has no TEMPLATES", module.__name__)
            continue

        if not callable(render_func):
            _LOGGER.warning("Template module %s has no render()", module.__name__)
            continue

        for template_name, meta in templates.items():
            if template_name in registry:
                raise ValueError(f"Duplicate template name: {template_name}")

            registry[template_name] = {
                **meta,
                "render": render_func,
                "module": module.__name__,
            }

    return registry