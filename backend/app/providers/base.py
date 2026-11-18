from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class GeneratedAsset:
    data: bytes
    content_type: str


class ImageProvider(Protocol):
    async def edit(self, photo: bytes, prompt: str) -> GeneratedAsset: ...


class VideoProvider(Protocol):
    async def image_to_video(self, image: bytes, prompt: str, *, image_url: Optional[str] = None) -> GeneratedAsset: ...
