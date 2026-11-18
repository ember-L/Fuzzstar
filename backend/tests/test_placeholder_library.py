"""占位片库构建与清单契约（FRD F03-4，ARCHITECTURE 分身资产管线）。"""
import hashlib
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

from app import placeholders

BODY_TYPES = ('slim', 'standard', 'chubby')
ACTIONS = ('idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right')


def probe(path: Path) -> dict:
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class BuildLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.manifest = placeholders.build_library(cls.root, version='vtest', width=320, height=180,
                                                  fps=12, duration=1.0, supersample=1)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_manifest_covers_three_body_types_times_seven_actions(self):
        self.assertEqual(self.manifest['version'], 'vtest')
        self.assertEqual(tuple(self.manifest['body_types']), BODY_TYPES)
        self.assertEqual(tuple(self.manifest['actions']), ACTIONS)
        for body_type in BODY_TYPES:
            for action in ACTIONS:
                clip = self.manifest['clips'][body_type][action]
                path = self.root / clip['file']
                self.assertTrue(path.is_file(), f'{body_type}/{action} missing')
                data = path.read_bytes()
                self.assertEqual(clip['bytes'], len(data))
                self.assertEqual(clip['sha256'], hashlib.sha256(data).hexdigest())

    def test_clips_are_silent_h264_within_spec(self):
        for body_type in BODY_TYPES:
            for action in ACTIONS:
                path = self.root / self.manifest['clips'][body_type][action]['file']
                streams = probe(path)['streams']
                video = [s for s in streams if s['codec_type'] == 'video']
                self.assertEqual(len(video), 1, f'{path.name} video streams')
                self.assertEqual(video[0]['codec_name'], 'h264')
                self.assertEqual((video[0]['width'], video[0]['height']), (320, 180))
                self.assertFalse([s for s in streams if s['codec_type'] == 'audio'], f'{path.name} has audio')
                self.assertLessEqual(float(video[0]['duration']), 5.0)

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as other:
            again = placeholders.build_library(Path(other), version='vtest', width=320, height=180,
                                               fps=12, duration=1.0, supersample=1)
        self.assertEqual(again['clips'], self.manifest['clips'])

    def test_frames_loop_align_at_full_period(self):
        for body_type in BODY_TYPES:
            for action in ACTIONS:
                first = placeholders.render_frame(body_type, action, 0.0, width=64, height=64)
                last = placeholders.render_frame(body_type, action, 2 * math.pi, width=64, height=64)
                self.assertEqual(first.tobytes(), last.tobytes(), f'{body_type}/{action} loop seam')


class LibraryLoadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        placeholders.build_library(self.root, version='vtest', width=320, height=180,
                                   fps=12, duration=1.0, supersample=1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_library_roundtrip(self):
        library = placeholders.load_library(self.root)
        self.assertEqual(library.manifest['version'], 'vtest')
        self.assertEqual(library.root, self.root)

    def test_load_library_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(placeholders.load_library(Path(empty)))

    def test_clip_path_whitelist(self):
        library = placeholders.load_library(self.root)
        self.assertEqual(library.clip_path('vtest', 'standard', 'idle'),
                         self.root / 'standard' / 'idle.mp4')
        for version, body_type, action in (('vother', 'standard', 'idle'), ('vtest', 'fat', 'idle'),
                                           ('vtest', 'standard', 'jump'), ('vtest', '../x', 'idle')):
            self.assertIsNone(library.clip_path(version, body_type, action))

    def test_manifest_payload_groups_urls(self):
        library = placeholders.load_library(self.root)
        payload = placeholders.manifest_payload(library, base_url='https://api.example/api/v1/avatar/placeholders')
        self.assertEqual(payload['version'], 'vtest')
        self.assertEqual(set(payload['groups']), set(BODY_TYPES))
        self.assertEqual(payload['groups']['chubby']['sick'],
                         'https://api.example/api/v1/avatar/placeholders/vtest/chubby/sick.mp4')


if __name__ == '__main__':
    unittest.main()
