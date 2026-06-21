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
    return f"""你是一个专业的网页内容分析助手。请分析以下从招聘网站抓取的页面内容，完成两个任务：

1. **目标匹配**：判断页面中是否包含用户关注的目标内容
2. **信息提取**：从页面中提取所有职位/岗位的结构化信息

[监控目标]
{target_desc}

[页面内容]
{content}

请按以下 JSON 格式回复（不要包含其他内容，不要用 markdown 代码块）：
{{
  "target_found": true 或 false,
  "summary": "简要概述页面内容和发现",
  "matched_items": [
    {{
      "company": "公司名称",
      "position": "岗位名称",
      "salary": "薪资范围（如有）",
      "location": "工作地点（如有）",
      "link": "详情链接（如有）",
      "tags": ["标签1", "标签2"],
      "match_reason": "匹配原因"
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
    """Send content + target to LLM and return a structured analysis dict with matched_items."""
    if not target_desc.strip():
        return {
            "target_found": False,
            "summary": "未设置爬虫目标，跳过分析",
            "matched_content": "",
            "matched_items": [],
            "reasoning": "",
        }

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
