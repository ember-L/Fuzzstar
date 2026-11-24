"""版本化初筛规则引擎：红线最先硬判定，其余按 YAML 分级；LLM 不参与（FRD F05-4/5）。"""

from dataclasses import dataclass
from pathlib import Path

import yaml

_CONDITION_KEYS = {'duration', 'frequency', 'spirit', 'appetite', 'severe'}
_SEVERITIES = ('observe', 'vet', 'urgent')


@dataclass(frozen=True)
class RulesBundle:
    symptoms: dict
    redlines: dict
    scoring: dict

    @property
    def rules_version(self) -> str:
        return f'{self.symptoms["version"]}+{self.redlines["version"]}'


def _version(data: dict, name: str) -> str:
    version = data.get('version')
    if not isinstance(version, str) or not 0 < len(version) <= 32:
        raise RuntimeError(f'{name}: version must be a non-empty string of at most 32 characters')
    return version


def _check_conditions(conditions, name: str):
    if not isinstance(conditions, list):
        raise RuntimeError(f'{name}: conditions must be a list')
    for condition in conditions:
        if not isinstance(condition, dict) or not condition or set(condition) - _CONDITION_KEYS:
            raise RuntimeError(f'{name}: unknown condition keys')
        for key, value in condition.items():
            if key == 'severe':
                if not isinstance(value, bool):
                    raise RuntimeError(f'{name}: severe condition must be boolean')
            elif not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                raise RuntimeError(f'{name}: condition values must be non-empty string lists')


def _load_symptoms(data: dict) -> dict:
    _version(data, 'symptoms')
    for key in ('duration_bands', 'frequency_bands', 'spirit_options', 'appetite_options'):
        value = data.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise RuntimeError(f'symptoms: {key} must be a non-empty string list')
    triggers = data.get('vet_triggers')
    if not isinstance(triggers, dict) or set(triggers) != {'spirit', 'appetite'}:
        raise RuntimeError('symptoms: vet_triggers must define spirit and appetite')
    for key, options in (('spirit', 'spirit_options'), ('appetite', 'appetite_options')):
        if not isinstance(triggers[key], list) or not set(triggers[key]) <= set(data[options]):
            raise RuntimeError(f'symptoms: vet_triggers.{key} must reference known options')
    if not isinstance(data.get('notes_max'), int) or data['notes_max'] <= 0:
        raise RuntimeError('symptoms: notes_max must be a positive integer')
    entries = data.get('symptoms')
    if not isinstance(entries, list) or not entries:
        raise RuntimeError('symptoms: symptom list must not be empty')
    codes = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('code'), str) or not entry['code']:
            raise RuntimeError('symptoms: each symptom needs a code')
        if (
            entry['code'] in codes
            or not isinstance(entry.get('label'), str)
            or not isinstance(entry.get('frequency'), bool)
        ):
            raise RuntimeError(f'symptoms: duplicate code or missing label/frequency for {entry.get("code")}')
        codes.add(entry['code'])
        _check_conditions(entry.get('observe', []), f'symptoms.{entry["code"]}.observe')
        _check_conditions(entry.get('vet', []), f'symptoms.{entry["code"]}.vet')
        if 'severe_label' in entry and not isinstance(entry['severe_label'], str):
            raise RuntimeError(f'symptoms: severe_label for {entry["code"]} must be a string')
    return data


def _load_redlines(data: dict, symptom_codes: set) -> dict:
    _version(data, 'redlines')
    entries = data.get('redlines')
    if not isinstance(entries, list) or not entries:
        raise RuntimeError('redlines: redline list must not be empty')
    option_codes = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get('code'), str)
            or not isinstance(entry.get('label'), str)
        ):
            raise RuntimeError('redlines: each redline needs code and label')
        options, derived = entry.get('options'), entry.get('derived')
        if options is None and derived is None:
            raise RuntimeError(f'redlines: {entry["code"]} needs options or a derived rule')
        if options is not None:
            if not isinstance(options, list) or not options:
                raise RuntimeError(f'redlines: {entry["code"]} options must not be empty')
            for option in options:
                if (
                    not isinstance(option, dict)
                    or not isinstance(option.get('code'), str)
                    or not isinstance(option.get('label'), str)
                ):
                    raise RuntimeError(f'redlines: {entry["code"]} option needs code and label')
                if option['code'] in option_codes:
                    raise RuntimeError(f'redlines: duplicate option {option["code"]}')
                option_codes.add(option['code'])
        if derived is not None and (
            not isinstance(derived, dict)
            or derived.get('symptom') not in symptom_codes
            or not isinstance(derived.get('duration'), list)
            or not derived['duration']
        ):
            raise RuntimeError(f'redlines: {entry["code"]} derived rule must reference a known symptom and durations')
    return data


def _load_scoring(data: dict) -> dict:
    _version(data, 'scoring')
    deltas = data.get('deltas')
    if (
        not isinstance(deltas, dict)
        or set(deltas) != set(_SEVERITIES)
        or not all(isinstance(v, int) and v > 0 for v in deltas.values())
    ):
        raise RuntimeError('scoring: deltas must define positive integers for observe/vet/urgent')
    decay = data.get('decay')
    if (
        not isinstance(decay, dict)
        or not isinstance(decay.get('observe_hours'), (int, float))
        or decay['observe_hours'] <= 0
    ):
        raise RuntimeError('scoring: decay.observe_hours must be positive')
    return data


def load_rules(directory: Path) -> RulesBundle | None:
    paths = {name: directory / f'{name}.yaml' for name in ('symptoms', 'redlines', 'scoring')}
    if not all(path.is_file() for path in paths.values()):
        return None
    data = {}
    for name, path in paths.items():
        loaded = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(loaded, dict):
            raise RuntimeError(f'{name}: rule file must be a mapping')
        data[name] = loaded
    symptoms = _load_symptoms(data['symptoms'])
    redlines = _load_redlines(data['redlines'], {s['code'] for s in symptoms['symptoms']})
    scoring = _load_scoring(data['scoring'])
    bundle = RulesBundle(symptoms=symptoms, redlines=redlines, scoring=scoring)
    if len(bundle.rules_version) > 32:
        raise RuntimeError('combined rules_version exceeds 32 characters')
    return bundle


def _symptom_index(bundle: RulesBundle) -> dict:
    return {s['code']: s for s in bundle.symptoms['symptoms']}


def validate_answers(bundle: RulesBundle, answers: dict) -> list:
    """返回 [{field, message}]；空列表表示可提交。字段定位供 AC-05-1/2。"""
    errors = []
    spec = bundle.symptoms
    for key, options, message in (
        ('spirit', spec['spirit_options'], '请选择精神状态'),
        ('appetite', spec['appetite_options'], '请选择食欲状态'),
    ):
        if answers.get(key) not in options:
            errors.append({'field': key, 'message': message})
    index = _symptom_index(bundle)
    seen = set()
    for i, item in enumerate(answers.get('symptoms') or []):
        prefix = f'symptoms[{i}]'
        code = item.get('code')
        if code not in index:
            errors.append({'field': f'{prefix}.code', 'message': '未知症状'})
            continue
        if code in seen:
            errors.append({'field': f'{prefix}.code', 'message': '症状重复'})
        seen.add(code)
        entry = index[code]
        if item.get('duration') not in spec['duration_bands']:
            errors.append({'field': f'{prefix}.duration', 'message': '请选择持续时长'})
        if entry['frequency'] and item.get('frequency') not in spec['frequency_bands']:
            errors.append({'field': f'{prefix}.frequency', 'message': '请选择频次'})
        notes = item.get('notes')
        if notes is not None and (not isinstance(notes, str) or len(notes) > spec['notes_max']):
            errors.append({'field': f'{prefix}.notes', 'message': f'备注不超过 {spec["notes_max"]} 字'})
        if 'severe' in item and not isinstance(item['severe'], bool):
            errors.append({'field': f'{prefix}.severe', 'message': '严重标志必须为布尔值'})
    option_codes = {o['code'] for r in bundle.redlines['redlines'] for o in r.get('options', [])}
    for i, option in enumerate(answers.get('redline_options') or []):
        if option not in option_codes:
            errors.append({'field': f'redline_options[{i}]', 'message': '未知红线选项'})
    return errors


def _matches(condition: dict, context: dict) -> bool:
    for key, value in condition.items():
        if key == 'severe':
            if context['severe'] != value:
                return False
        elif context.get(key) not in value:
            return False
    return True


def triage(bundle: RulesBundle, answers: dict) -> dict:
    """红线最先；随后基础项触发；多症状取最高档。纯函数，同版本可复现。"""
    hits = []
    option_map = {o['code']: r['code'] for r in bundle.redlines['redlines'] for o in r.get('options', [])}
    selected = {s['code']: s for s in answers.get('symptoms') or []}
    for redline in bundle.redlines['redlines']:
        code = redline['code']
        explicit = any(option_map.get(o) == code for o in answers.get('redline_options') or [])
        derived = redline.get('derived')
        derived_hit = False
        if derived:
            item = selected.get(derived['symptom'])
            derived_hit = item is not None and item.get('duration') in derived['duration']
        if explicit or derived_hit:
            hits.append(code)
    grades = {}
    for code, item in selected.items():
        entry = _symptom_index(bundle)[code]
        context = {
            'duration': item.get('duration'),
            'frequency': item.get('frequency'),
            'spirit': answers.get('spirit'),
            'appetite': answers.get('appetite'),
            'severe': bool(item.get('severe', False)),
        }
        grades[code] = 'vet' if any(_matches(c, context) for c in entry.get('vet', [])) else 'observe'
    if hits:
        state = 'urgent'
    elif (
        answers.get('spirit') in bundle.symptoms['vet_triggers']['spirit']
        or answers.get('appetite') in bundle.symptoms['vet_triggers']['appetite']
    ) or 'vet' in grades.values():
        state = 'vet'
    elif grades:
        state = 'observe'
    else:
        state = 'normal'
    return {
        'state': state,
        'redline_hit': bool(hits),
        'redlines': hits,
        'symptom_grades': grades,
        'rules_version': bundle.rules_version,
    }


def symptoms_config(bundle: RulesBundle) -> dict:
    spec = bundle.symptoms
    return {
        'version': spec['version'],
        'duration_bands': spec['duration_bands'],
        'frequency_bands': spec['frequency_bands'],
        'spirit_options': spec['spirit_options'],
        'appetite_options': spec['appetite_options'],
        'vet_triggers': spec['vet_triggers'],
        'notes_max': spec['notes_max'],
        'symptoms': [
            {'code': s['code'], 'label': s['label'], 'frequency': s['frequency'], 'severe_label': s.get('severe_label')}
            for s in spec['symptoms']
        ],
        'redlines': [
            {
                'code': r['code'],
                'label': r['label'],
                **({'options': r['options']} if 'options' in r else {}),
                **({'derived': r['derived']} if 'derived' in r else {}),
            }
            for r in bundle.redlines['redlines']
        ],
    }
