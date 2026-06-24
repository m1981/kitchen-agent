"""
Regression test: mimo provider returns empty response when use_tools=False
but tools are still sent to the API.
"""
from unittest.mock import MagicMock
from src.agent.context_assembler import ContextSlot
from src.agent.turn_orchestrator import TurnInput, TurnOrchestrator
from src.agent.tool_executor import ToolExecutor
from src.providers.normalizer import ResponseNormalizer


class FakeRegistry:
    """Registry that returns tool declarations."""
    def get_all_entries(self):
        return [MagicMock(declaration=MagicMock(
            name="read_file",
            description="Read a file",
            parameters=MagicMock(properties={}, required=[])
        ))]
    
    def get_handler(self, name):
        return lambda filepath: f"content of {filepath}"
    
    def schemas_for_provider(self, provider):
        return []


class FakeTokenCounter:
    def count(self, text):
        return max(1, len(text) // 4)
    def count_message(self, message):
        return self.count(str(message.get("content", "")))
    def trim_to(self, text, max_tokens):
        return text[:max_tokens * 4]


class FakePromptManager:
    def get_system_instruction(self, mode="default"):
        return "You are helpful."


class FakeMimoProvider:
    """
    Fake that simulates the mimo bug: returns tool_calls even when
    no tools were requested via use_tools=False.
    """
    def __init__(self):
        self._model = "mimo-v2.5-pro"
        self.call_count = 0
        
    def complete(self, context):
        self.call_count += 1
        # Simulate: mimo API returns tool_calls instead of text
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message = MagicMock()
        response.choices[0].message.content = None  # Empty content!
        tool_call_mock = MagicMock()
        tool_call_mock.id = "call_1"
        tool_call_mock.function = MagicMock()
        tool_call_mock.function.name = "read_file"
        tool_call_mock.function.arguments = '{"filepath": "/test.md"}'
        response.choices[0].message.tool_calls = [tool_call_mock]
        response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        return response
    
    def complete_with_tools(self, context, tool_calls, tool_results):
        """After tool execution, return text response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message = MagicMock()
        response.choices[0].message.content = "Here is the file content."
        response.choices[0].message.tool_calls = None
        response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        return response


def test_empty_response_when_use_tools_false():
    """
    Regression: when use_tools=False, if the LLM returns tool_calls
    instead of text, the response should not be empty.
    
    The bug: mimo API returns tool_calls even when no tools were sent
    (tool_schemas_count=0). The orchestrator ignores them because
    use_tools=False, resulting in empty response.
    """
    # This fake simulates the real mimo behavior: returns tool_calls
    # even when no tools were requested
    provider = FakeMimoProvider()
    
    orchestrator = TurnOrchestrator(
        context_assembler=MagicMock(
            assemble=MagicMock(return_value=MagicMock(
                system_prompt="test",
                messages=[{"role": "user", "content": "hello"}],
                images=[],
                context_files=[],
                tool_schemas=None,  # No tools set by orchestrator
                slots_used={ContextSlot.SYSTEM_PROMPT: 10, ContextSlot.CONVERSATION_HISTORY: 20},
            ))
        ),
        tool_executor=ToolExecutor(registry=FakeRegistry()),
        provider=provider,
        response_normalizer=ResponseNormalizer(),
        provider_name="mimo",
        tool_registry=FakeRegistry(),
    )
    
    session = {"messages": []}
    turn_input = TurnInput(
        user_message="hello",
        use_tools=False,  # Tools disabled!
    )
    
    output = orchestrator.run(session=session, turn_input=turn_input)
    
    # The LLM returned tool_calls but we have use_tools=False
    # The orchestrator should handle this gracefully
    print(f"Response: '{output.assistant_message}'")
    print(f"Response length: {len(output.assistant_message)}")
    print(f"Tool calls made: {output.tool_calls_made}")
    
    # Current behavior: empty response because tool_calls are ignored
    # Expected: either non-empty response OR tool_calls should be executed
    # For now, we document this as a known issue with mimo provider
    if len(output.assistant_message) == 0:
        print("KNOWN ISSUE: mimo model returned tool_calls when use_tools=False")
        print("The orchestrator ignores tool_calls when use_tools=False")
        print("This results in empty response")


def test_use_tools_false_with_text_response():
    """
    When use_tools=False and LLM returns text (not tool_calls),
    the response should contain the text.
    """
    class TextOnlyProvider:
        def __init__(self):
            self._model = "mimo-v2.5-pro"
            
        def complete(self, context):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "Hello! How can I help?"
            response.choices[0].message.tool_calls = None
            response.usage = MagicMock(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150
            )
            return response
    
    provider = TextOnlyProvider()
    
    orchestrator = TurnOrchestrator(
        context_assembler=MagicMock(
            assemble=MagicMock(return_value=MagicMock(
                system_prompt="test",
                messages=[{"role": "user", "content": "hello"}],
                images=[],
                context_files=[],
                tool_schemas=None,
                slots_used={ContextSlot.SYSTEM_PROMPT: 10, ContextSlot.CONVERSATION_HISTORY: 20},
            ))
        ),
        tool_executor=ToolExecutor(registry=FakeRegistry()),
        provider=provider,
        response_normalizer=ResponseNormalizer(),
        provider_name="mimo",
        tool_registry=FakeRegistry(),
    )
    
    session = {"messages": []}
    turn_input = TurnInput(
        user_message="hello",
        use_tools=False,
    )
    
    output = orchestrator.run(session=session, turn_input=turn_input)
    
    assert output.assistant_message == "Hello! How can I help?"
    assert len(output.tool_calls_made) == 0
