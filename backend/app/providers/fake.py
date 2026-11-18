import io

from PIL import Image

from app.providers.base import GeneratedAsset


class FakeImageProvider:
    def __init__(self):
        self.calls = []

    async def edit(self, photo: bytes, prompt: str) -> GeneratedAsset:
        self.calls.append(prompt)
        encoded = io.BytesIO()
        Image.new('RGB', (4, 4), (200, 120, 60)).save(encoded, 'PNG')
        return GeneratedAsset(encoded.getvalue(), 'image/png')


class FakeVideoProvider:
    def __init__(self, fail_actions=()):
        self.fail_actions = set(fail_actions)
        self.calls = []

    async def image_to_video(self, image: bytes, prompt: str, *, image_url=None) -> GeneratedAsset:
        self.calls.append(prompt)
        if any(action in prompt for action in self.fail_actions):
            raise RuntimeError(f'fake provider failure for {prompt}')
        return GeneratedAsset(b'fake-video:' + prompt.encode(), 'video/mp4')
