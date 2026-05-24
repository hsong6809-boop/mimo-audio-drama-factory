"""MiMo API 统一调用封装

支持文本生成和 TTS 合成，内置重试、限流、错误处理。
"""

import json
import time
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get


class MiMoAPIError(Exception):
    """MiMo API 调用异常"""

    def __init__(self, status_code: int, message: str, response: Any = None):
        self.status_code = status_code
        self.message = message
        self.response = response
        super().__init__(f"[{status_code}] {message}")


class MiMoClient:
    """MiMo 大模型 + TTS 统一客户端"""

    def __init__(self, api_key: str | None = None):
        self.api_base = get("mimo", "api_base", "https://api.mimo.xiaomi.com/v1")
        self.model = get("mimo", "model", "mimo-large")
        self.timeout = get("mimo", "timeout", 120)
        self.api_key = api_key or self._load_api_key()

        self._http = httpx.Client(
            base_url=self.api_base,
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        # 简单限流：两次调用间最少间隔
        self._min_interval = 0.5
        self._last_call_time = 0.0

    def _load_api_key(self) -> str:
        """从环境变量或配置文件加载 API Key"""
        import os

        key = os.environ.get("MIMO_API_KEY", "")
        if not key:
            logger.warning("未设置 MIMO_API_KEY，API 调用将失败")
        return key

    def _throttle(self):
        """简单限流"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, MiMoAPIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_format: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> str:
        """
        文本生成（Chat Completion）

        Args:
            prompt: 用户提示词
            system: 系统提示词
            response_format: 输出格式（"json" 或 None）
            temperature: 温度
            max_tokens: 最大 token 数

        Returns:
            模型输出文本
        """
        self._throttle()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}

        logger.debug(f"MiMo generate: {len(prompt)} chars prompt")

        resp = self._http.post("/chat/completions", json=body)

        if resp.status_code != 200:
            raise MiMoAPIError(resp.status_code, resp.text, resp)

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        logger.debug(f"MiMo response: {len(content)} chars")
        return content

    def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> dict:
        """生成并解析 JSON 输出"""
        raw = self.generate(
            prompt, system=system, response_format="json",
            temperature=temperature, max_tokens=max_tokens,
        )
        # 兼容模型输出中包含 markdown 代码块的情况
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 去掉首尾的 ``` 行
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)

    def tts_synthesize(
        self,
        text: str,
        voice_id: str,
        speed: float = 1.0,
        pitch: int = 0,
        volume: float = 1.0,
        output_path: str | None = None,
    ) -> bytes:
        """
        TTS 语音合成

        Args:
            text: 要合成的文本
            voice_id: 音色 ID
            speed: 语速（0.5-2.0）
            pitch: 音调偏移（-10 到 +10）
            volume: 音量（0.0-2.0）
            output_path: 输出文件路径（可选）

        Returns:
            音频二进制数据（WAV 格式）
        """
        self._throttle()

        body = {
            "model": "mimo-tts",
            "input": text,
            "voice": voice_id,
            "speed": speed,
            "pitch": pitch,
            "volume": volume,
            "response_format": "wav",
        }

        logger.debug(f"TTS synthesize: '{text[:30]}...' voice={voice_id}")

        resp = self._http.post("/audio/speech", json=body)

        if resp.status_code != 200:
            raise MiMoAPIError(resp.status_code, resp.text, resp)

        audio_data = resp.content

        if output_path:
            with open(output_path, "wb") as f:
                f.write(audio_data)
            logger.debug(f"TTS saved: {output_path} ({len(audio_data)} bytes)")

        return audio_data

    def close(self):
        """关闭 HTTP 客户端"""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
