"""
src/providers
=============
LLM provider abstraction package.

Exports:
  LLMProvider  — the runtime-checkable Protocol all providers implement.
  get_provider — factory that returns the configured provider instance.
"""
from src.providers.base import LLMProvider, get_provider

__all__ = ["LLMProvider", "get_provider"]
