"""去 AI 味静态 lint 模块（纯规则、无 LLM 依赖）。"""
from app.deslop.lint import scan

__all__ = ["scan"]