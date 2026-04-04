from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class BasePanelData:
    theme: str = ""
    template: str = ""
    updated: str = ""
    lang: str = "ja"


@dataclass
class HasImagePanelData(BasePanelData):
    image_path: str = ""
    photo_preset: str | None = None
    resolved_photo_preset: str | None = None
    photo_avg_luma: float | None = None
    photo_contrast: float | None = None


@dataclass
class TodayPanelData(HasImagePanelData):
    date: str = ""
    weekday: str = ""
    weather: str = ""
    temperature: str = ""
    rain: str = ""
    schedule: Sequence[str] = field(default_factory=list)
    home_status: Sequence[str] = field(default_factory=list)
    message: str = ""


@dataclass
class NoticePanelData(BasePanelData):
    title: str = ""
    body: str = ""
    date: str = ""
    weekday: str = ""
    level: str = "info"
    icon: str = ""


PanelData = TodayPanelData | NoticePanelData
