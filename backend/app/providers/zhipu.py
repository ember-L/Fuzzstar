"""智谱 AI（ZhipuAI / GLM）适配器。

使用 OpenAI 兼容的 chat/completions 接口。
默认模型 glm-4-flash：速度最快、无深度思考、免费额度，
适合聊天与护理建议这类需要快速响应的场景。
last_usage 供 ai_usage_logs 审计，与 DashScopeLLMProvider 保持同接口。
"""

import httpx

ZHIPU_BASE = 'https://open.bigmodel.cn/api/paas/v4'


class ZhipuError(RuntimeError):
    pass


class ZhipuLLMProvider:
    """智谱 glm-4-flash 文本生成。与 DashScopeLLMProvider 同接口可互换。"""

    provider = 'zhipu'

    def __init__(self, api_key: str, model: str = 'glm-4-flash', timeout: float = 60, transport=None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport
        self.last_usage: dict | None = None

    async def chat(self, messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 800) -> str:
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
            # 关闭深度思考，追求最快响应
            'thinking': {'type': 'disabled'},
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                f'{ZHIPU_BASE}/chat/completions',
                json=payload,
                headers={'Authorization': f'Bearer {self.api_key}'},
            )
            data = response.json()
            if response.status_code != 200:
                raise ZhipuError(f'zhipu chat failed: {data}')
            try:
                content = data['choices'][0]['message']['content']
            except (KeyError, IndexError, TypeError) as exc:
                raise ZhipuError(f'zhipu chat returned no content: {data}') from exc
            usage = data.get('usage') or {}
            self.last_usage = {
                'tokens_in': usage.get('prompt_tokens'),
                'tokens_out': usage.get('completion_tokens'),
            }
            return content
