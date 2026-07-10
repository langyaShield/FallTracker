"""
LLM analysis for the radar crawler (AI-driven mode).

负责：调用 LLM 分析抓取内容，同时完成目标匹配 + 结构化信息提取。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings as global_settings
from app.crypto import decrypt_value
from app.database import SessionLocal
from app.models import UserSettings
from app.services.radar.fetcher import MAX_RAW_TEXT_CHARS  # noqa: F401  (re-export)

logger = logging.getLogger("falltracker.radar.llm")


def fetch_user_llm_config(user_id: int) -> Dict[str, Optional[str]]:
    """Pre-fetch user LLM config in a single DB roundtrip."""
    db = SessionLocal()
    try:
        s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    finally:
        db.close()

    return {
        "llm_api_key": (decrypt_value(s.llm_api_key) if s and s.llm_api_key else global_settings.LLM_API_KEY) or "",
        "llm_api_base": (s.llm_api_base if s and s.llm_api_base else global_settings.LLM_API_BASE) or "",
        "llm_model": (s.llm_model if s and s.llm_model else global_settings.LLM_MODEL) or "",
    }


def _build_prompt(target_desc: str, content: str) -> str:
    # 监控目标为空时，退化为通用的「页面更新/值得关注内容」检测，保证容错性
    if target_desc.strip():
        goal_block = f"[监控目标]\n{target_desc.strip()}"
        goal_hint = "判断页面中是否包含与「监控目标」相关的内容或更新"
    else:
        goal_block = "[监控目标]\n（用户未指定具体目标，请检测页面是否有值得关注的内容或更新）"
        goal_hint = "判断页面是否有值得用户关注的内容或更新"

    return f"""你是一个通用的网页内容分析助手。请分析以下抓取到的网页内容，完成两个任务：

1. **目标判断**：{goal_hint}
2. **信息提取**：从页面中提取所有值得关注的结构化信息条目。若页面是招聘类内容，请填写公司/岗位/薪资等字段；若是其他类型内容（公告、商品、资讯等），可将关键信息填入 company/position 字段或留空，并在 match_reason 中说明。

{goal_block}

[页面内容]
{content}

请按以下 JSON 格式回复（不要包含其他内容，不要用 markdown 代码块）：
{{
  "target_found": true 或 false,
  "summary": "简要概述页面内容和发现",
  "matched_items": [
    {{
      "company": "公司名称（招聘场景填写，其他场景可留空）",
      "position": "岗位名称或条目标题（招聘场景填岗位，其他场景可填条目标题）",
      "salary": "薪资范围（如有，否则留空）",
      "location": "工作地点或相关位置（如有，否则留空）",
      "link": "详情链接（如有）",
      "tags": ["标签1", "标签2"],
      "match_reason": "该条目值得关注的原因或与目标的匹配说明"
    }}
  ],
  "reasoning": "分析推理过程"
}}"""


def _call_llm_sync(prompt: str, api_key: str, api_base: str, model: str) -> str:
    """Synchronous LLM call. Returns the raw assistant text content."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4000,
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()
    return result["choices"][0]["message"]["content"].strip()


def _parse_llm_response(llm_text: str) -> Dict[str, Any]:
    """Try to extract a JSON object from the LLM response. Falls back to a typed default."""
    json_match = re.search(r"\{[\s\S]*\}", llm_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            parsed = {}
        return {
            "target_found": bool(parsed.get("target_found", False)),
            "summary": parsed.get("summary", ""),
            "matched_content": parsed.get("summary", ""),  # backward compat
            "matched_items": parsed.get("matched_items", []),
            "reasoning": parsed.get("reasoning", ""),
        }
    return {
        "target_found": False,
        "summary": "LLM 返回格式异常",
        "matched_content": "",
        "matched_items": [],
        "reasoning": llm_text[:500],
    }


def analyze_with_llm(target_desc: str, content: str, llm_config: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """Send content + target to LLM and return a structured analysis dict with matched_items.

    target_desc 为空时不再跳过分析，而是退化为通用的「页面更新检测」，
    保证用户即使只想抓取通知也能获得有效的分析结果。
    """
    if not content.strip() or content.startswith("(页面"):
        return {
            "target_found": False,
            "summary": "页面内容获取失败，无法分析",
            "matched_content": "",
            "matched_items": [],
            "reasoning": content,
        }

    api_key = llm_config.get("llm_api_key") or ""
    api_base = llm_config.get("llm_api_base") or ""
    model = llm_config.get("llm_model") or ""

    if not api_key:
        return {
            "target_found": False,
            "summary": "LLM API Key 未配置",
            "matched_content": "",
            "matched_items": [],
            "reasoning": "请在设置中配置 LLM API Key",
        }

    prompt = _build_prompt(target_desc, content)

    try:
        llm_text = _call_llm_sync(prompt, api_key, api_base, model)
        return _parse_llm_response(llm_text)
    except Exception as e:
        logger.exception("LLM analysis failed: %s", e)
        return {
            "target_found": False,
            "summary": f"LLM 分析异常: {str(e)[:100]}",
            "matched_content": "",
            "matched_items": [],
            "reasoning": str(e)[:500],
        }
