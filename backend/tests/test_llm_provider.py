"""T10 LLM Provider：Fake 与 DashScope qwen-max 适配（httpx MockTransport）。"""

import json
import unittest

import httpx

from app.providers.dashscope import DashScopeError, DashScopeLLMProvider
from app.providers.fake import FakeLLMProvider

MESSAGES = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]
REPLY = '{"text": "建议观察精神与食欲。", "tips": ["记录变化"]}'


class FakeLLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_returns_reply_and_records_usage(self):
        provider = FakeLLMProvider(REPLY)
        text = await provider.chat(MESSAGES, temperature=0.2, max_tokens=500)
        self.assertEqual(text, REPLY)
        self.assertEqual(provider.calls, [{'messages': MESSAGES, 'temperature': 0.2, 'max_tokens': 500}])
        self.assertEqual(provider.last_usage, {'tokens_in': 100, 'tokens_out': 30})

    async def test_fail_times_raises_then_recovers(self):
        provider = FakeLLMProvider(REPLY, fail_times=2)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                await provider.chat(MESSAGES)
        self.assertEqual(await provider.chat(MESSAGES), REPLY)


class DashScopeLLMTests(unittest.IsolatedAsyncioTestCase):
    def _provider(self, handler):
        return DashScopeLLMProvider('test-key', transport=httpx.MockTransport(handler))

    async def test_success_request_shape_and_usage(self):
        seen = {}

        def handler(request):
            seen['url'] = str(request.url)
            seen['auth'] = request.headers.get('Authorization')
            seen['body'] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    'output': {'choices': [{'message': {'content': REPLY}}]},
                    'usage': {'input_tokens': 120, 'output_tokens': 40},
                },
            )

        provider = self._provider(handler)
        text = await provider.chat(MESSAGES, temperature=0.2, max_tokens=600)
        self.assertEqual(text, REPLY)
        self.assertEqual(seen['url'], 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation')
        self.assertEqual(seen['auth'], 'Bearer test-key')
        body = seen['body']
        self.assertEqual(body['model'], 'qwen-max')
        self.assertEqual(body['input']['messages'], MESSAGES)
        self.assertEqual(body['parameters']['result_format'], 'message')
        self.assertEqual(body['parameters']['temperature'], 0.2)
        self.assertEqual(body['parameters']['max_tokens'], 600)
        self.assertEqual(provider.last_usage, {'tokens_in': 120, 'tokens_out': 40})

    async def test_http_error_raises(self):
        provider = self._provider(lambda request: httpx.Response(429, json={'code': 'Throttling'}))
        with self.assertRaises(DashScopeError):
            await provider.chat(MESSAGES)

    async def test_missing_content_raises(self):
        provider = self._provider(lambda request: httpx.Response(200, json={'output': {'choices': []}}))
        with self.assertRaises(DashScopeError):
            await provider.chat(MESSAGES)


if __name__ == '__main__':
    unittest.main()
