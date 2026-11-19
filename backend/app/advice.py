"""初筛建议：状态档模板、LLM 提示词与输出守卫（FRD F05-6/7）。

LLM 仅生成观察/记录/就医建议文本，不参与分级、打分与红线决策。
输出约定 JSON {text, tips}；解析失败或含禁词（确诊/治疗）抛 AdviceError，
由 worker 重试（≤2 次）后降级为模板建议。
"""
import json
import re
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

FORBIDDEN_WORDS = ('确诊', '治疗')
STATES = ('normal', 'observe', 'vet', 'urgent')
_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$', re.IGNORECASE)

SYSTEM_PROMPT = (
    '你是宠物健康记录助手。只生成观察、记录与就医准备建议,不做诊断,不开具处方。'
    '输出严禁出现「确诊」「治疗」字样。'
    '仅输出 JSON:{"text": "一段总体建议(不超过120字)", "tips": ["3到4条可执行建议"]}。'
)


class AdviceError(ValueError):
    """LLM 输出不可用（格式错误或含禁词），应重试或降级。"""


def load_advice_templates(directory: Path) -> Optional[dict]:
    path = Path(directory) / 'advice_templates.yaml'
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        version = data['version']
        states = data['states']
        if not isinstance(version, str) or not version or len(version) > 32:
            raise ValueError('bad version')
        if set(states) != set(STATES):
            raise ValueError('states must cover normal/observe/vet/urgent')
        for state in STATES:
            entry = states[state]
            text, tips = entry['text'], entry['tips']
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f'{state}: empty text')
            if not isinstance(tips, list) or not tips or not all(isinstance(t, str) and t.strip() for t in tips):
                raise ValueError(f'{state}: bad tips')
            blob = text + ''.join(tips)
            if any(word in blob for word in FORBIDDEN_WORDS):
                raise ValueError(f'{state}: forbidden word in template')
        return {'version': version, 'states': states}
    except Exception as exc:
        raise RuntimeError(f'invalid advice_templates.yaml: {exc}') from exc


def template_advice(templates: dict, state: str) -> dict:
    entry = templates['states'][state]
    return {'source': 'template', 'text': entry['text'], 'tips': list(entry['tips']),
            'template_version': templates['version']}


def build_advice_messages(screening: dict, symptoms: list[dict]) -> list[dict]:
    lines = [f"初筛状态档:{screening['state']}", f"精神:{screening['spirit']}", f"食欲:{screening['appetite']}",
             f"规则版本:{screening['rules_version']}", '症状清单:']
    if symptoms:
        for s in symptoms:
            parts = [f"- {s['label']}({s['code']})", f"时长:{s['duration']}"]
            if s.get('frequency'):
                parts.append(f"频次:{s['frequency']}")
            if s.get('notes'):
                parts.append(f"备注:{s['notes']}")
            parts.append('严重度:是' if s.get('severe') else '严重度:否')
            if s.get('grade'):
                parts.append(f"分级:{s['grade']}")
            lines.append(' '.join(parts))
    else:
        lines.append('- 无症状')
    return [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': '\n'.join(lines)}]


def parse_advice(raw: str) -> dict:
    cleaned = _FENCE.sub('', raw.strip())
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AdviceError('advice output is not valid JSON') from exc
    if not isinstance(data, dict):
        raise AdviceError('advice output must be a JSON object')
    text = data.get('text')
    tips = data.get('tips')
    if not isinstance(text, str) or not text.strip():
        raise AdviceError('advice text missing')
    if not isinstance(tips, list) or not all(isinstance(t, str) for t in tips):
        raise AdviceError('advice tips must be a list of strings')
    text = text.strip()
    tips = [t.strip() for t in tips if t.strip()]
    if len(text) > 1000 or len(tips) > 8:
        raise AdviceError('advice output too long')
    blob = text + ''.join(tips)
    if any(word in blob for word in FORBIDDEN_WORDS):
        raise AdviceError('advice contains forbidden wording')
    return {'text': text, 'tips': tips}


def _usage_row(task, screening, llm_provider, *, failed: bool):
    from app.models import AiUsageLog
    usage = None if failed else (getattr(llm_provider, 'last_usage', None) or {})
    return AiUsageLog(user_id=screening.user_id if screening is not None else None,
                      task_id=task.id, provider=getattr(llm_provider, 'provider', 'fake'),
                      model=getattr(llm_provider, 'model', 'fake'), kind='llm',
                      tokens_in=usage.get('tokens_in') if usage else None,
                      tokens_out=usage.get('tokens_out') if usage else None)


async def analyze_screening(engine, task, *, llm_provider, templates, rules=None) -> dict:
    """执行 screening_analysis：LLM 仅写建议文本；成功持久化 llm_advice/advice_json 与用量。"""
    from app.models import HealthScreening, ScreeningSymptom
    screening_id = task.payload['screening_id']
    with Session(engine) as db:
        screening = db.get(HealthScreening, screening_id)
        if screening is None:
            raise ValueError(f'screening {screening_id} not found')
        rows = db.scalars(select(ScreeningSymptom).where(ScreeningSymptom.screening_id == screening_id)
                          .order_by(ScreeningSymptom.id)).all()
        labels = {s['code']: s['label'] for s in rules.symptoms['symptoms']} if rules is not None else {}
        grades = (screening.triage_json or {}).get('symptom_grades', {})
        symptoms = [{'code': r.symptom_code, 'label': labels.get(r.symptom_code, r.symptom_code),
                     'duration': r.duration, 'frequency': r.frequency, 'notes': r.notes,
                     'severe': r.severe, 'grade': grades.get(r.symptom_code)} for r in rows]
        info = {'state': screening.state, 'spirit': screening.spirit, 'appetite': screening.appetite,
                'rules_version': screening.rules_version}
    messages = build_advice_messages(info, symptoms)
    raw = await llm_provider.chat(messages, temperature=0.3, max_tokens=800)
    advice = parse_advice(raw)
    with Session(engine) as db, db.begin():
        screening = db.get(HealthScreening, screening_id)
        screening.llm_advice = advice['text']
        screening.advice_json = {'source': 'llm', 'text': advice['text'], 'tips': advice['tips'],
                                 'model': getattr(llm_provider, 'model', 'fake')}
        db.add(_usage_row(task, screening, llm_provider, failed=False))
    return {'screening_id': screening_id, 'source': 'llm'}


def record_llm_failure(engine, task_id, llm_provider) -> None:
    from app.models import HealthScreening, Task
    with Session(engine) as db, db.begin():
        task = db.get(Task, task_id)
        screening = db.get(HealthScreening, task.payload.get('screening_id'))
        db.add(_usage_row(task, screening, llm_provider, failed=True))


def apply_template_fallback(engine, task_id, templates) -> None:
    """重试耗尽后持久化模板建议；已有 LLM 建议不覆盖。"""
    from app.models import HealthScreening, Task
    with Session(engine) as db, db.begin():
        task = db.get(Task, task_id)
        screening = db.get(HealthScreening, task.payload.get('screening_id'))
        if screening is None or screening.llm_advice is not None or screening.advice_json is not None:
            return
        screening.advice_json = template_advice(templates, screening.state)
