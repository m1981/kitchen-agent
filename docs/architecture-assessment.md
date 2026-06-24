# Kitchen Agent — Architecture Assessment

Honest evaluation of the Kitchen Agent tool-calling implementation against
modern coding agent architectures (OpenAI Agents SDK, Anthropic multi-agent
research system, Temporal agentic loops, LangChain, and production patterns
from Anthropic/OpenAI engineering blogs).

**Date:** 2026-06-11
**Scope:** Backend agent layer only (tool registration → execution → persistence)

---

## What I Compared Against

| Implementation                           | Source           | Key Pattern                                                                |
| ---------------------------------------- | ---------------- | -------------------------------------------------------------------------- |
| **OpenAI Agents SDK**                    | Official SDK     | Built-in agent loop, guardrails, tracing, handoffs, sessions               |
| **Anthropic multi-agent research**       | Engineering blog | Parallel subagents, token budget as primary performance lever              |
| **Anthropic long-running agent harness** | Engineering blog | Initializer + coding agent, progress artifacts, context window management  |
| **Anthropic tool design principles**     | Engineering blog | Tools designed _for agents_, not developers; evaluation harnesses          |
| **Temporal agentic loop**                | Docs             | Durable workflows, retry at orchestration level, dynamic tool registration |
| **LangChain / LlamaIndex**               | Open source      | Unified provider interface, chain composition                              |

---

## What You're Doing Right (Above Average)

### 1. Protocol-based provider abstraction

Your `LLMProvider` Protocol is cleaner than most implementations. Many
projects (including early LangChain) used abstract base classes that tightly
coupled providers. Your Protocol approach means providers don't even need to
import a base module.

### 2. ToolEntry binding

This is genuinely clever. Binding `declaration + fn + category` in a single
frozen dataclass eliminates the #1 bug in agent systems: schema/callable
drift. The OpenAI Agents SDK uses decorators (`@function_tool`) which is
elegant but less explicit. Your approach is more testable.

### 3. ResponseNormalizer

Most multi-provider systems normalize at the _request_ level (convert
everything to OpenAI format before sending). You normalize at the _response_
level, which is more resilient because you don't lose provider-specific
features during the outbound path.

### 4. Common format for persistence

Storing history in a provider-agnostic common format and converting on reload
is the right call. This is exactly what Anthropic recommends in their tool use
docs. The `tool_call_id` bug (fixed in `58b98c1`) was a missing converter,
not an architectural flaw.

### 5. Error wrapping in ToolExecutor

`ToolResult(is_error=True)` instead of crashing is textbook. Anthropic's
engineering blog specifically calls this out: "Never crash the turn — return
structured error to LLM."

### 6. Context budget management

Your `ContextBudget` with slot-based allocation is ahead of most hobbyist
implementations. Most just dump everything into the context window and hope.

---

## Where You're Behind Production-Grade Agents

### 1. No retry/backoff for tool failures

```python
# Your current code:
result = handler(**tool_call.arguments)  # fails → error sent to LLM

# What OpenAI Agents SDK does:
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def execute_with_retry(func, args):
    return await asyncio.wait_for(asyncio.to_thread(func, **args), timeout=30.0)
```

Your `ToolExecutor` catches exceptions and wraps them, but doesn't retry.
For transient failures (network, file locks), the LLM has to "notice" the
error and retry the tool call itself — wasting a full LLM round-trip.

**Impact:** Medium. Your tools are local filesystem ops, so transient failures
are rare. But if you add web search or API calls, this becomes critical.

### 2. No parallel tool execution

```python
# Your current code (sequential):
return [self._execute_one(tc) for tc in tool_calls]

# What you could do:
async def execute_all(self, tool_calls):
    return await asyncio.gather(*[self._execute_one(tc) for tc in tool_calls])
```

When the LLM returns multiple tool calls (e.g., `read_file("a.md")` +
`read_file("b.md")`), you execute them sequentially. Anthropic's research
found that parallel tool execution is one of the biggest performance
multipliers.

**Impact:** Low-Medium. Your tools are fast (local I/O), so sequential is
fine. But the pattern matters if you scale.

### 3. No token budget enforcement during the tool loop

This is the **biggest gap**. Anthropic's research paper found that **token
usage explains 80% of performance variance** in agentic systems. Your
`ContextAssembler` budgets the initial context, but during the tool loop:

```python
while normalized.has_tool_calls:
    # Tool results are appended to conversation_state
    # But nobody checks if we're exceeding the context window
    tool_results = self._tools.execute_all(normalized.tool_calls)
    raw = provider.complete_with_tools(context, tool_calls, tool_results)
```

Each tool result adds tokens. After 5-10 iterations, you can blow past the
model's context limit. The OpenAI Agents SDK and Anthropic's harness both
have context management (compaction, truncation of old tool results).

**Impact:** High. This will bite you when tools return large results (e.g.,
`search_knowledge_base` returning 200 matches).

### 4. No evaluation harness for tools

Anthropic's engineering blog emphasizes: _"Build an evaluation to measure
how well Claude uses your tools."_ You have unit tests for tool
_implementations_, but no eval for tool _usage quality_ (does the LLM call
the right tool with the right args? does it recover from errors?).

**Impact:** Medium. You can't improve what you can't measure.

### 5. No MCP (Model Context Protocol) support

The OpenAI Agents SDK, Claude Code, and Cursor all support MCP now. Your
tool registry is custom, which works fine but means you can't plug in
community MCP servers.

**Impact:** Low for now. But the ecosystem is moving toward MCP as the
standard.

### 6. No tracing/observability beyond structlog

The OpenAI Agents SDK has built-in tracing that visualizes the full agent
loop. You have `structlog` with timing, but no trace visualization, no
latency breakdown per tool, no cost tracking per turn.

**Impact:** Medium. Critical for debugging production issues.

---

## What You're Doing That's _Different_ (Not Better or Worse)

### 1. Backup/revert pattern

I haven't seen this in other agent implementations. Every mutating tool
snapshots before changing. This is a smart UX pattern for a knowledge-base
editing agent. Most coding agents just rely on git.

### 2. Dual history (API + UI)

You maintain separate `api_history` (for the LLM) and `ui_history` (for
the frontend). This is pragmatic — the UI needs `turn_id`, tool logs,
provider metadata that the LLM doesn't need. Most frameworks store one
history and filter.

### 3. Prompt modes

The `PromptManager` with mode-specific system prompts (default, coding,
etc.) is a nice touch. Most agents have a single static system prompt.

---

## Scorecard

| Dimension                | Your Implementation   | Industry Standard       | Verdict            |
| ------------------------ | --------------------- | ----------------------- | ------------------ |
| **Provider abstraction** | Protocol + Normalizer | ABC + format conversion | ✅ Above average   |
| **Tool registration**    | ToolEntry binding     | Decorators / MCP        | ✅ Above average   |
| **Error handling**       | Wrap, don't crash     | Wrap + retry            | ⚠️ Missing retry   |
| **Context management**   | Budget on entry       | Budget + compaction     | ⚠️ No loop budget  |
| **History persistence**  | Common format         | Provider-specific       | ✅ Above average   |
| **Streaming**            | Full SSE pipeline     | Varies                  | ✅ Good            |
| **Observability**        | structlog + timing    | Tracing + cost tracking | ⚠️ Basic           |
| **Parallel execution**   | Sequential            | Async gather            | ⚠️ Sequential      |
| **Tool eval harness**    | None                  | Automated evals         | ❌ Missing         |
| **MCP support**          | None                  | Growing standard        | ❌ Missing         |
| **Multi-agent**          | Single agent          | Parallel subagents      | N/A (not needed)   |
| **Backup/revert**        | Built-in              | Git-based               | ✅ Unique strength |

---

## Verdict

**Your implementation is above average for a single-agent, multi-provider
system.** The architecture is clean, well-layered, and the common format
pattern is the right call. The recent `tool_call_id` bug was a missing
converter, not an architectural flaw — and the fix pattern (one converter
per provider) is exactly how Anthropic and OpenAI recommend handling it.

**The two things that would move you from "good" to "production-grade":**

1. **Token budget enforcement in the tool loop** — truncate or compact tool
   results when approaching context limits. This is the #1 performance lever
   according to Anthropic's research.

2. **Retry with backoff in ToolExecutor** — even a simple 2-retry with
   exponential backoff would cover the edge cases where tools fail transiently.

---

## References

- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Temporal: Basic Agentic Loop with Tool Calling](https://docs.temporal.io/ai-cookbook/agentic-loop-tool-call-openai-python)
- [Anthropic: Tool use with Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
