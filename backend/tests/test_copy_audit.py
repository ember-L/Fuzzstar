"""T19 文案审计：固定用户可见文案与 FRD 一字不差（FRD.md:338、342-348）。

回归锁：任何常量漂移都会在这里失败；移动端产品文案同样锁定。
"""
import re
import unittest
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import audio, chat, feeding, gif, screening_api
from app.auth import APIError, utcnow
from app.models import Base, UsageCounter, User
from app.quota import quota_gate

BACKEND = Path(__file__).resolve().parents[1]
MOBILE = BACKEND.parent / 'mobile' / 'src' / 'lib'

DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断'
REDLINE_TITLE = '建议立即就医'
REDLINE_SUBTITLE = '该症状可能危及生命,请不要等待观察,尽快前往具备急诊能力的宠物医院。'
PREPARATION = ['带上本条记录与存证照片/视频', '出发前电话确认医院急诊能力',
               '疑似中毒请携带可疑物品包装,勿自行催吐', '勿擅自喂食人用药物']
FEEDING_FOOTER = '以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。'
AUDIO_FOOTER = '情绪解读为娱乐性参考,置信度仅供判断展示。'


def mobile_constant(filename, name):
    text = (MOBILE / filename).read_text(encoding='utf-8')
    match = re.search(r"export const " + name + r" = '([^']*)';", text)
    if match is None:
        raise AssertionError(f'{filename} missing constant {name}')
    return match.group(1)


class CopyAuditTests(unittest.TestCase):
    def test_disclaimer_verbatim_in_chat_and_screening(self):
        self.assertEqual(chat.CHAT_DISCLAIMER, DISCLAIMER)
        self.assertEqual(screening_api.DISCLAIMER, DISCLAIMER)

    def test_redline_card_verbatim(self):
        card = screening_api.REDLINE_CARD
        self.assertEqual(card['title'], REDLINE_TITLE)
        self.assertEqual(card['subtitle'], REDLINE_SUBTITLE)
        self.assertEqual(card['preparation'], PREPARATION)

    def test_chat_redline_guidance_matches_card(self):
        config = chat.load_chat_config(BACKEND / 'rules')
        response = chat.redline_response(config)
        self.assertEqual(response['guidance']['title'], REDLINE_TITLE)
        self.assertEqual(response['guidance']['text'], REDLINE_SUBTITLE)
        self.assertEqual(response['guidance']['route'], 'screening')

    def test_feeding_footer_verbatim(self):
        self.assertEqual(feeding.FEEDING_DISCLAIMER, FEEDING_FOOTER)

    def test_audio_footer_verbatim(self):
        self.assertEqual(audio.AUDIO_FOOTER, AUDIO_FOOTER)

    def test_quota_denial_message_says_tomorrow(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        now = utcnow()
        with Session(engine) as db, db.begin():
            db.add(User(id=1, nickname='审计用户'))
            db.add(UsageCounter(user_id=1, metric='screening', day=now.date(), count=100))
        with Session(engine) as db:
            with self.assertRaises(APIError) as caught:
                quota_gate(db, 1, 'screening', now=now)
        error = caught.exception
        self.assertEqual(error.status, 429)
        self.assertEqual(error.code, 'QUOTA_EXCEEDED')
        self.assertIn('明日再试', error.message)
        engine.dispose()

    def test_gif_watermark_text(self):
        self.assertEqual(gif.WATERMARK_TEXT, '绒星 · AI 参考')

    def test_urgent_template_tips_match_checklist(self):
        templates = yaml.safe_load((BACKEND / 'rules' / 'advice_templates.yaml').read_text(encoding='utf-8'))
        urgent = templates['states']['urgent']
        self.assertEqual(urgent['tips'], PREPARATION)
        self.assertIn('急诊', urgent['text'])

    def test_mobile_product_copy_locked(self):
        self.assertEqual(mobile_constant('account.ts', 'DELETION_NOTICE'),
                         '注销后账号将被冻结、无法登录；15 天内数据保留但不可访问，到期后所有数据（含云端照片与视频）将被物理清除，无法恢复。')
        self.assertEqual(mobile_constant('account.ts', 'DELETION_CONFIRM_LABEL'), '我已了解，确认注销')
        self.assertEqual(mobile_constant('account.ts', 'TRAINING_NOTICE'),
                         '是否允许绒星将你的匿名使用数据用于模型训练？默认不允许；拒绝不影响任何功能，你可以随时更改。')
        self.assertEqual(mobile_constant('quota.ts', 'QUOTA_EXHAUSTED_HINT'), '今日次数已用完，明日再试')
        self.assertEqual(mobile_constant('gif-export.ts', 'GIF_SHARE_HINT'),
                         'GIF 已添加「绒星 · AI 参考」水印，仅通过系统分享面板发送，不会上传第三方。')
        self.assertEqual(mobile_constant('weight.ts', 'SCREENING_SUGGESTION'), '建议做一次健康初筛')


if __name__ == '__main__':
    unittest.main()
