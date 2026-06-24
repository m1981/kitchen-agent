"""
src/agent/
==========
Agent layer — LLM turn lifecycle, tool execution, and context assembly.

Components
----------
  - ``tool_executor``     — safe, isolated tool execution
  - ``context_assembler`` — builds the context window
  - ``turn_orchestrator`` — manages one turn end-to-end

Provider implementations
------------------------
- Gemini  → ``src/providers/gemini.py``
- Anthropic → ``src/providers/anthropic_provider.py``

Adding a new provider
---------------------
1. Implement ``LLMProvider`` protocol in a new file under ``src/providers/``.
2. Register it in ``src/providers/base.py :: get_provider()``.
3. Add the key to ``settings.llm_provider`` docs in ``config.py``.
This package does NOT need to change.
"""
