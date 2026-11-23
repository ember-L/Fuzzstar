import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.env import load_env, parse_env


class ParseEnvTests(unittest.TestCase):
    def test_ignores_comments_and_blank_lines(self):
        self.assertEqual(parse_env('# comment\n\nA=1\n   # indented\nB=2\n'), {'A': '1', 'B': '2'})

    def test_strips_export_prefix_and_matching_quotes(self):
        self.assertEqual(parse_env('export A="one two"\nB=\'three\'\n'), {'A': 'one two', 'B': 'three'})

    def test_keeps_equals_signs_inside_values(self):
        value = 'mysql+pymysql://u:p@127.0.0.1:3306/rongxing?charset=utf8mb4'
        self.assertEqual(parse_env(f'DATABASE_URL={value}'), {'DATABASE_URL': value})

    def test_skips_lines_without_a_key_or_separator(self):
        self.assertEqual(parse_env('=broken\nNO_SEPARATOR\n'), {})


class LoadEnvTests(unittest.TestCase):
    def test_missing_file_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_env(Path(tmp) / 'absent.env'), {})

    def test_process_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('PRESENT=new\nMISSING=filled\n', encoding='utf-8')
            with patch.dict(os.environ, {'PRESENT': 'keep'}, clear=True):
                self.assertEqual(load_env(path), {'PRESENT': 'new', 'MISSING': 'filled'})
                self.assertEqual(os.environ['PRESENT'], 'keep')
                self.assertEqual(os.environ['MISSING'], 'filled')


if __name__ == '__main__':
    unittest.main()
