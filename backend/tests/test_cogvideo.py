"""CogVideoX-Flash 接入：提示词转写、首帧构图、限流退避与 GIF 规格。"""
import asyncio
import io
import unittest

import httpx
from PIL import Image

from app.providers.cogvideo import CogVideoError, CogVideoMotionProvider, build_prompt, square_frame
from app.services.motion import verify_gif


def make_photo(size=(234, 282), color=(255, 236, 215)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, 'PNG')
    return buffer.getvalue()


class BuildPromptTest(unittest.TestCase):
    def test_strips_action_token_and_tech_note(self):
        prompt = build_prompt('idle 待机：轻呼吸、慢眨眼，身体小幅起伏，首尾帧对齐可无缝循环')
        self.assertNotIn('idle', prompt)
        self.assertNotIn('无缝循环', prompt)
        self.assertIn('轻呼吸', prompt)

    def test_keeps_action_meaning(self):
        prompt = build_prompt('play 玩耍：前爪扑动，追着自己的尾巴转半圈')
        self.assertIn('前爪扑动', prompt)
        self.assertLessEqual(len(prompt), 512)


class SquareFrameTest(unittest.TestCase):
    def test_produces_square_image(self):
        frame = square_frame(make_photo(), size=256)
        image = Image.open(io.BytesIO(frame))
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(image.format, 'JPEG')


class WatermarkFilterTest(unittest.TestCase):
    def test_box_covers_logo_and_keeps_margin(self):
        from app.providers.cogvideo import LOGO_MARGIN, watermark_filter
        text = watermark_filter(1024, 1024)
        values = dict(part.split('=') for part in text[len('delogo:'):].split(':') if '=' in part)
        x, y, w, h = (int(values[key]) for key in ('x', 'y', 'w', 'h'))
        # 角标实测右界 0.992W、下界 0.977H，框必须盖住且不贴边（delogo 会判越界）。
        self.assertLessEqual(x, 1024 * 0.846)
        self.assertLessEqual(y, 1024 * 0.925)
        self.assertGreaterEqual(x + w, 1024 * 0.992)
        self.assertGreaterEqual(y + h, 1024 * 0.977)
        self.assertLess(x + w, 1024)
        self.assertLess(y + h, 1024)
        self.assertEqual(LOGO_MARGIN, 6)


class ProviderTest(unittest.TestCase):
    def _provider(self, **overrides):
        options = {'api_key': 'test-key', 'submit_attempts': 1, 'poll_interval': 0.01}
        options.update(overrides)
        return CogVideoMotionProvider(**options)

    @staticmethod
    def _with_client(handler, action):
        """httpx 异步客户端不支持 with 语法，这里用协程包一层。"""
        async def main():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await action(client)
        return asyncio.run(main())

    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            CogVideoMotionProvider(api_key='')

    def test_submit_retries_on_rate_limit(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, json={'error': {'code': '1305', 'message': 'busy'}})
            return httpx.Response(200, json={'id': 'task-1'})

        provider = self._provider(submit_attempts=3)
        task_id = self._with_client(
            handler, lambda client: provider._submit(client, {'model': 'cogvideox-flash'}))
        self.assertEqual(task_id, 'task-1')
        self.assertEqual(len(calls), 2)

    def test_submit_gives_up_after_attempts(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={'error': {'code': '1305', 'message': 'busy'}})

        provider = self._provider(submit_attempts=1)
        with self.assertRaises(CogVideoError):
            self._with_client(handler,
                              lambda client: provider._submit(client, {'model': 'cogvideox-flash'}))

    def test_watermark_flag_dropped_when_rejected(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json
            body = json.loads(request.content)
            seen.append(body)
            if 'watermark_enabled' in body:
                return httpx.Response(403, json={'error': {'message': 'not signed'}})
            return httpx.Response(200, json={'id': 'task-2'})

        provider = self._provider(submit_attempts=3)
        task_id = self._with_client(
            handler, lambda client: provider._submit(
                client, {'model': 'cogvideox-flash', 'watermark_enabled': False}))
        self.assertEqual(task_id, 'task-2')
        self.assertNotIn('watermark_enabled', seen[-1])

    def test_poll_returns_on_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={'task_status': 'SUCCESS',
                                             'video_result': [{'url': 'https://example.com/v.mp4'}]})

        provider = self._provider()
        result = self._with_client(handler, lambda client: provider._poll(client, 'task-1'))
        self.assertEqual(result['task_status'], 'SUCCESS')

    def test_enchant_keeps_photo_identity(self):
        photo = make_photo()
        asset = asyncio.run(self._provider().enchant(photo, prompt='萌化'))
        self.assertEqual(asset.content_type, 'image/png')
        self.assertEqual(Image.open(io.BytesIO(asset.data)).size, (234, 282))


class GifSpecTest(unittest.TestCase):
    def test_generated_gif_meets_motion_spec(self):
        from app.providers.cogvideo import mp4_to_gif
        ffmpeg = None
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            self.skipTest('imageio-ffmpeg is not installed')
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            source = f'{folder}/clip.mp4'
            subprocess.run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'testsrc=size=640x640:rate=30:duration=3', source], check=True)
            gif = mp4_to_gif(open(source, 'rb').read(), fps=12, height=480)
        spec = verify_gif(gif, max_seconds=7, max_height=480)
        self.assertLessEqual(spec['height'], 480)
        self.assertLessEqual(spec['duration_s'], 7)


if __name__ == '__main__':
    unittest.main()
