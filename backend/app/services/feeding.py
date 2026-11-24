"""T12 喂养参考：附录 E 纯公式（RER/DER、生命阶段系数、能量密度）。

系数与密度来自 rules/feeding.yaml（可调）；输出一律携带「参考值,非医嘱」尾注。
"""

from datetime import date, datetime
from pathlib import Path

import yaml

FEEDING_DISCLAIMER = '以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。'

COEFFICIENT_KEYS = ('kitten_under_4m', 'kitten_4_12m', 'adult_neutered', 'adult_intact', 'senior')
FOOD_TYPES = ('dry', 'wet', 'snack', 'other')


def load_feeding_config(directory: Path) -> dict | None:
    path = directory / 'feeding.yaml'
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise RuntimeError('feeding.yaml must be a mapping')
    version = data.get('version')
    if not isinstance(version, str) or not version or len(version) > 32:
        raise RuntimeError('feeding.yaml version must be a non-empty string of at most 32 characters')
    densities = data.get('densities')
    if not isinstance(densities, dict):
        raise RuntimeError('feeding.yaml densities must be a mapping')
    for key in ('dry', 'wet'):
        value = densities.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f'feeding.yaml densities.{key} must be a positive number')
    coefficients = data.get('coefficients')
    if not isinstance(coefficients, dict):
        raise RuntimeError('feeding.yaml coefficients must be a mapping')
    for key in COEFFICIENT_KEYS:
        value = coefficients.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f'feeding.yaml coefficients.{key} must be a positive number')
    for key in ('rer_factor', 'rer_exponent'):
        value = data.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f'feeding.yaml {key} must be a positive number')
    return data


def kcal_estimate(config: dict, food_type: str, amount_g: float) -> float | None:
    density = config['densities'].get(food_type)
    if density is None:
        return None
    return round(amount_g * density, 1)


def _calendar_months(birth: date, now: datetime) -> int:
    months = (now.year - birth.year) * 12 + (now.month - birth.month)
    if now.day < birth.day:
        months -= 1
    return months


def life_stage(birth_date: date | None, neutered: bool, *, now: datetime) -> str:
    if birth_date is not None:
        months = _calendar_months(birth_date, now)
        if months < 4:
            return 'kitten_under_4m'
        if months < 12:
            return 'kitten_4_12m'
        if months >= 132:
            return 'senior'
    return 'adult_neutered' if neutered else 'adult_intact'


def feeding_reference(
    config: dict, *, weight_kg: float, birth_date: date | None, neutered: bool, now: datetime
) -> dict:
    stage = life_stage(birth_date, neutered, now=now)
    coefficient = config['coefficients'][stage]
    rer = config['rer_factor'] * (weight_kg ** config['rer_exponent'])
    der = rer * coefficient
    dry_g = round(der / config['densities']['dry'], 1)
    wet_g = round(der / config['densities']['wet'], 1)
    return {
        'weight_kg': weight_kg,
        'life_stage': stage,
        'coefficient': coefficient,
        'rer_kcal': round(rer, 1),
        'der_kcal': round(der, 1),
        'dry_g': dry_g,
        'wet_g': wet_g,
        'dry_g_range': [round(dry_g * 0.9, 1), round(dry_g * 1.1, 1)],
        'wet_g_range': [round(wet_g * 0.9, 1), round(wet_g * 1.1, 1)],
        'disclaimer': FEEDING_DISCLAIMER,
    }
