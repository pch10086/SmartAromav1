"""Qwen via ModelScope inference (OpenAI SDK) or DashScope (httpx)."""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from smart_aroma.config import Settings, get_settings, has_api_key, uses_modelscope
from smart_aroma.llm.json_extract import parse_aroma_plan
from smart_aroma.llm.prompt import SYSTEM_PROMPT, user_prompt_for_request
from smart_aroma.models.sequence_schema import AromaPlan, mock_plan_for_request

log = logging.getLogger(__name__)


class QwenClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def chat_completion(self, user_message: str) -> str:
        s = self._settings
        if uses_modelscope(s):
            return self._chat_modelscope(user_message)
        if s.dashscope_api_key and s.dashscope_api_key.strip():
            return self._chat_dashscope(user_message)
        raise RuntimeError("No LLM API key configured")

    def _chat_modelscope(self, user_message: str) -> str:
        s = self._settings
        base = s.modelscope_base_url.rstrip("/")
        client = OpenAI(
            base_url=base,
            api_key=s.modelscope_api_key,
            timeout=120.0,
        )
        log.info("Calling ModelScope chat.completions model=%s", s.modelscope_model)
        response = client.chat.completions.create(
            model=s.modelscope_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.55,
            stream=False,
        )
        choice = response.choices[0]
        content = (choice.message.content or "").strip()
        if not content:
            raise ValueError("Empty completion content from ModelScope")
        log.info("ModelScope response length=%s chars", len(content))
        return content

    def _chat_dashscope(self, user_message: str) -> str:
        s = self._settings
        url = f"{s.dashscope_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {s.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": s.qwen_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.55,
        }
        log.info("Calling DashScope chat_completions model=%s", s.qwen_model)
        with httpx.Client(timeout=120.0) as http:
            r = http.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        log.info("DashScope response length=%s chars", len(content or ""))
        return content or ""


def generate_plan_from_llm(
    scene: str,
    persona: str,
    duration_level: str,
    settings: Settings | None = None,
) -> AromaPlan:
    """Return validated plan from API, or mock if no API key."""
    s = settings or get_settings()
    if not has_api_key(s):
        log.warning(
            "MOCK_PLAN: no LLM API key; using built-in plan for scene=%s persona=%s duration_level=%s",
            scene,
            persona,
            duration_level,
        )
        return mock_plan_for_request(scene, persona, duration_level)

    client = QwenClient(s)
    raw = client.chat_completion(user_prompt_for_request(scene, persona, duration_level))
    try:
        plan = parse_aroma_plan(raw, AromaPlan)
    except Exception as e:
        log.exception("Failed to parse LLM JSON: %s", e)
        raise

    log.info(
        "LLM plan generated scene=%s persona=%s duration_level=%s total_duration_sec=%s",
        plan.scene,
        plan.persona,
        plan.duration_level,
        plan.total_duration_sec,
    )
    return plan
