from __future__ import annotations

import json
from typing import Any

import httpx

from backend.core.config import Settings


class HerbKnowledgeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze_model_comparison(self, comparison_payload: dict[str, Any]) -> dict[str, Any]:
        if not self.is_enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "summary": "尚未配置 AI API Key，暂不生成模型对比分析。",
                "strengths_model_a": [],
                "strengths_model_b": [],
                "recommendations": [],
            }

        payload = {
            "model": self.settings.ai.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名目标检测模型评估助手。请根据两个模型对同一批图片的检测统计结果，"
                        "输出严格 JSON，字段必须为 summary、strengths_model_a、strengths_model_b、recommendations。"
                        "除 summary 外，其余字段必须是字符串数组，内容使用简体中文。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请分析以下两个模型对同一批图片的检测结果表现差异，并给出改进建议。"
                        f"数据：{json.dumps(comparison_payload, ensure_ascii=False)}。"
                        "输出 JSON，不要使用 markdown 代码块。"
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.ai.timeout_seconds) as client:
                response = await client.post(
                    self._chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.ai.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "summary": f"AI 调用失败：{exc}",
                "strengths_model_a": [],
                "strengths_model_b": [],
                "recommendations": [],
            }

        content = response.json()["choices"][0]["message"]["content"]
        parsed = self._parse_comparison_content(content)
        parsed["enabled"] = True
        parsed["status"] = "success"
        return parsed

    async def generate_for_candidates(self, herb_candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
        normalized_candidates = [candidate for candidate in (herb_candidates or []) if candidate.get("herb_name")]
        if not normalized_candidates:
            return {
                "enabled": self.is_enabled,
                "status": "skipped",
                "items": [],
                "notes": "未识别到可用于知识生成的中草药名称。",
            }

        if not self.is_enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "items": [
                    {
                        "herb_name": candidate["herb_name"],
                        "count": candidate.get("count", 1),
                        "max_confidence": candidate.get("max_confidence", 0),
                        "basic_description": "",
                        "medicinal_effects": [],
                        "notes": "尚未配置 AI API Key，暂不生成草药介绍。",
                    }
                    for candidate in normalized_candidates
                ],
                "notes": "尚未配置 AI API Key，暂不生成草药介绍。",
            }

        herb_names = [candidate["herb_name"] for candidate in normalized_candidates]
        knowledge_items = await self._generate_batch(herb_names)
        knowledge_map = {item.get("herb_name"): item for item in knowledge_items if item.get("herb_name")}

        merged_items = []
        for candidate in normalized_candidates:
            item = knowledge_map.get(candidate["herb_name"], {})
            merged_items.append(
                {
                    "herb_name": candidate["herb_name"],
                    "count": candidate.get("count", 1),
                    "max_confidence": candidate.get("max_confidence", 0),
                    "basic_description": item.get("basic_description", ""),
                    "medicinal_effects": item.get("medicinal_effects", []),
                    "notes": item.get("notes", ""),
                }
            )

        return {
            "enabled": True,
            "status": "success",
            "items": merged_items,
            "notes": "AI 已按识别到的中草药种类归一化生成介绍。",
        }

    async def generate(self, herb_name: str | None) -> dict[str, Any]:
        if not herb_name:
            return {
                "enabled": self.is_enabled,
                "status": "skipped",
                "herb_name": None,
                "basic_description": "",
                "medicinal_effects": [],
                "notes": "未识别到可用于知识生成的中草药名称。",
            }

        if not self.is_enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "herb_name": herb_name,
                "basic_description": "",
                "medicinal_effects": [],
                "notes": "尚未配置 AI API Key，暂不生成草药介绍。",
            }

        payload = {
            "model": self.settings.ai.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名中草药知识助手。请根据用户给出的中草药名称，输出严格 JSON，"
                        "字段必须为 herb_name、basic_description、medicinal_effects、notes。"
                        "其中 medicinal_effects 必须是字符串数组，内容使用简体中文。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请介绍中草药“{herb_name}”。"
                        "输出 JSON，不要使用 markdown 代码块。"
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.ai.timeout_seconds) as client:
                response = await client.post(
                    self._chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.ai.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error",
                "herb_name": herb_name,
                "basic_description": "",
                "medicinal_effects": [],
                "notes": f"AI 调用失败：{exc}",
            }

        content = response.json()["choices"][0]["message"]["content"]
        parsed = self._parse_content(content)
        return {
            "enabled": True,
            "status": "success",
            "herb_name": parsed.get("herb_name") or herb_name,
            "basic_description": parsed.get("basic_description", ""),
            "medicinal_effects": parsed.get("medicinal_effects", []),
            "notes": parsed.get("notes", ""),
            "raw": content,
        }

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.ai.api_key.strip())

    @property
    def _chat_completions_url(self) -> str:
        return f"{self.settings.ai.base_url.rstrip('/')}/chat/completions"

    async def _generate_batch(self, herb_names: list[str]) -> list[dict[str, Any]]:
        payload = {
            "model": self.settings.ai.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名中草药知识助手。请根据用户提供的多个中草药名称，输出严格 JSON 数组。"
                        "数组每一项必须包含 herb_name、basic_description、medicinal_effects、notes。"
                        "其中 medicinal_effects 必须是字符串数组，内容使用简体中文。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请分别介绍以下中草药，并按每一种单独输出简介和药用功效："
                        f"{', '.join(herb_names)}。输出 JSON 数组，不要使用 markdown 代码块。"
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.ai.timeout_seconds) as client:
                response = await client.post(
                    self._chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self.settings.ai.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except Exception as exc:
            return [
                {
                    "herb_name": herb_name,
                    "basic_description": "",
                    "medicinal_effects": [],
                    "notes": f"AI 调用失败：{exc}",
                }
                for herb_name in herb_names
            ]

        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_batch_content(content, herb_names)

    @staticmethod
    def _parse_content(content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            normalized = normalized.replace("json", "", 1).strip()

        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                medicinal_effects = parsed.get("medicinal_effects") or []
                if not isinstance(medicinal_effects, list):
                    medicinal_effects = [str(medicinal_effects)]
                parsed["medicinal_effects"] = medicinal_effects
                return parsed
        except json.JSONDecodeError:
            pass

        return {
            "herb_name": "",
            "basic_description": normalized,
            "medicinal_effects": [],
            "notes": "模型未严格返回 JSON，已回退为纯文本描述。",
        }

    @staticmethod
    def _parse_batch_content(content: str, herb_names: list[str]) -> list[dict[str, Any]]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            normalized = normalized.replace("json", "", 1).strip()

        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, list):
                normalized_items = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    medicinal_effects = item.get("medicinal_effects") or []
                    if not isinstance(medicinal_effects, list):
                        medicinal_effects = [str(medicinal_effects)]
                    normalized_items.append(
                        {
                            "herb_name": item.get("herb_name", ""),
                            "basic_description": item.get("basic_description", ""),
                            "medicinal_effects": medicinal_effects,
                            "notes": item.get("notes", ""),
                        }
                    )
                if normalized_items:
                    return normalized_items
        except json.JSONDecodeError:
            pass

        return [
            {
                "herb_name": herb_name,
                "basic_description": normalized,
                "medicinal_effects": [],
                "notes": "模型未严格返回 JSON 数组，已回退为纯文本描述。",
            }
            for herb_name in herb_names
        ]

    @staticmethod
    def _parse_comparison_content(content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            normalized = normalized.replace("json", "", 1).strip()

        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return {
                    "summary": parsed.get("summary", ""),
                    "strengths_model_a": parsed.get("strengths_model_a", []) if isinstance(parsed.get("strengths_model_a", []), list) else [str(parsed.get("strengths_model_a"))],
                    "strengths_model_b": parsed.get("strengths_model_b", []) if isinstance(parsed.get("strengths_model_b", []), list) else [str(parsed.get("strengths_model_b"))],
                    "recommendations": parsed.get("recommendations", []) if isinstance(parsed.get("recommendations", []), list) else [str(parsed.get("recommendations"))],
                }
        except json.JSONDecodeError:
            pass

        return {
            "summary": normalized,
            "strengths_model_a": [],
            "strengths_model_b": [],
            "recommendations": [],
        }
