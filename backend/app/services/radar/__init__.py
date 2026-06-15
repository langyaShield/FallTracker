"""
Radar service package.

按职责拆分的子模块：
- fetcher: HTTP 抓取与 HTML 解析
- llm: LLM 分析与 JSON 解析
- email: SMTP 邮件通知
- engine: 单次爬虫执行编排
- scheduler: 后台调度器

调用方建议通过 `from app.services.radar import fetcher, llm, ...`
按需导入，避免循环依赖。
"""
from app.services.radar import email, engine, fetcher, llm, scheduler

__all__ = ["email", "engine", "fetcher", "llm", "scheduler"]
