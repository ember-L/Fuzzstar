"""T12 喂养参考纯公式（附录 E）：RER/DER、生命阶段系数、能量密度与免责尾注。"""
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from app.services.feeding import (
    FEEDING_DISCLAIMER,
    kcal_estimate,
    life_stage,
    load_feeding_config,
    feeding_reference,
)

RULES_DIR = Path(__file__).resolve().parents[1] / 'rules'
NOW = datetime(2026, 11, 19, 12, 0, 0)


class FeedingConfigTests(unittest.TestCase):
    def test_loads_real_config(self):
        config = load_feeding_config(RULES_DIR)
        self.assertIsNotNone(config)
        self.assertEqual(config['version'], 'fd-2026-11-19')
        self.assertEqual(config['densities']['dry'], 3.8)
        self.assertEqual(config['densities']['wet'], 0.9)
        self.assertEqual(config['coefficients']['adult_neutered'], 1.2)

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_feeding_config(Path(tmp)))

    def test_invalid_config_raises(self):
        cases = [
            'version: ' + 'x' * 33 + '\ndensities: {dry: 3.8, wet: 0.9}\ncoefficients: {kitten_under_4m: 3.0, kitten_4_12m: 2.0, adult_neutered: 1.2, adult_intact: 1.4, senior: 1.1}\nrer_factor: 70\nrer_exponent: 0.75\n',
            'version: fd-1\ndensities: {dry: -1, wet: 0.9}\ncoefficients: {kitten_under_4m: 3.0, kitten_4_12m: 2.0, adult_neutered: 1.2, adult_intact: 1.4, senior: 1.1}\nrer_factor: 70\nrer_exponent: 0.75\n',
            'version: fd-1\ndensities: {dry: 3.8, wet: 0.9}\ncoefficients: {kitten_under_4m: 3.0}\nrer_factor: 70\nrer_exponent: 0.75\n',
        ]
        for text in cases:
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / 'feeding.yaml').write_text(text, encoding='utf-8')
                with self.assertRaises(RuntimeError, msg=text[:40]):
                    load_feeding_config(Path(tmp))


class KcalTests(unittest.TestCase):
    def setUp(self):
        self.config = load_feeding_config(RULES_DIR)

    def test_ac_07_2_dry_50g_is_190(self):
        self.assertEqual(kcal_estimate(self.config, 'dry', 50), 190.0)

    def test_wet_density_and_rounding(self):
        self.assertEqual(kcal_estimate(self.config, 'wet', 100), 90.0)
        self.assertEqual(kcal_estimate(self.config, 'dry', 33.3), 126.5)

    def test_snack_and_other_have_no_kcal(self):
        self.assertIsNone(kcal_estimate(self.config, 'snack', 20))
        self.assertIsNone(kcal_estimate(self.config, 'other', 20))


class LifeStageTests(unittest.TestCase):
    def test_stages_by_calendar_months(self):
        cases = [
            (date(2026, 9, 20), False, 'kitten_under_4m'),   # ~2 月龄
            (date(2026, 5, 19), False, 'kitten_4_12m'),     # 6 月龄
            (date(2024, 1, 1), True, 'adult_neutered'),
            (date(2024, 1, 1), False, 'adult_intact'),
            (date(2014, 1, 1), True, 'senior'),             # ≥11 岁优先
            (None, True, 'adult_neutered'),                 # 无生日按成年
            (None, False, 'adult_intact'),
        ]
        for birth, neutered, expected in cases:
            with self.subTest(birth=birth, neutered=neutered):
                self.assertEqual(life_stage(birth, neutered, now=NOW), expected)

    def test_month_boundary_day_adjustment(self):
        # 2026-07-20 出生：到 2026-11-19 未满 4 个日历月（差 1 天）
        self.assertEqual(life_stage(date(2026, 7, 20), False, now=NOW), 'kitten_under_4m')
        self.assertEqual(life_stage(date(2026, 7, 19), False, now=NOW), 'kitten_4_12m')


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.config = load_feeding_config(RULES_DIR)

    def test_ac_07_4_4kg_neutered_adult(self):
        ref = feeding_reference(self.config, weight_kg=4.0, birth_date=date(2024, 1, 1), neutered=True, now=NOW)
        self.assertAlmostEqual(ref['rer_kcal'], 198.0, delta=0.5)
        self.assertAlmostEqual(ref['der_kcal'], 238.0, delta=1.0)
        self.assertAlmostEqual(ref['dry_g'], 63.0, delta=1.0)
        self.assertAlmostEqual(ref['wet_g'], 264.0, delta=2.0)
        self.assertEqual(ref['life_stage'], 'adult_neutered')
        self.assertEqual(ref['coefficient'], 1.2)
        self.assertEqual(ref['disclaimer'], FEEDING_DISCLAIMER)

    def test_gram_ranges_are_ten_percent_band(self):
        ref = feeding_reference(self.config, weight_kg=4.0, birth_date=None, neutered=True, now=NOW)
        lo, hi = ref['dry_g_range']
        self.assertAlmostEqual(lo, ref['dry_g'] * 0.9, delta=0.1)
        self.assertAlmostEqual(hi, ref['dry_g'] * 1.1, delta=0.1)
        wlo, whi = ref['wet_g_range']
        self.assertAlmostEqual(wlo, ref['wet_g'] * 0.9, delta=0.1)
        self.assertAlmostEqual(whi, ref['wet_g'] * 1.1, delta=0.1)

    def test_kitten_coefficient_triples_rer(self):
        ref = feeding_reference(self.config, weight_kg=2.0, birth_date=date(2026, 9, 1), neutered=False, now=NOW)
        self.assertEqual(ref['coefficient'], 3.0)
        self.assertAlmostEqual(ref['der_kcal'], ref['rer_kcal'] * 3.0, delta=0.2)

    def test_disclaimer_verbatim(self):
        self.assertEqual(FEEDING_DISCLAIMER, '以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。')


if __name__ == '__main__':
    unittest.main()
