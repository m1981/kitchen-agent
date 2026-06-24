## 🔧 The Current SDK: `google-genai`

The modern package is `google-genai` (not the old `google-generativeai`). Install it:

```bash
pip install google-genai
```

Set your API key:

```bash
export GEMINI_API_KEY="your_key_here"
```

---

## 📐 How Function Calling Works (2025/2026)

Function calling lets you connect models to external tools and APIs. Instead of generating text responses, the model determines when to call specific functions and provides the necessary parameters to execute real-world actions.

The three main use cases are augmenting knowledge (external APIs/DBs), extending capabilities (calculators, code), and taking actions (scheduling, emails, smart home).

> **⚠️ Important for Gemini 3+ models:** Gemini 3 model APIs now generate a unique `id` for every function call. When returning the result of your executed function to the model, you should pass the matching `id` in your `functionResponse`. If you are using the standard Python or Node.js SDKs, this is handled automatically.

---

## ✅ Complete Python Example (latest pattern)---

## 🗺️ Key Concepts Summary

**The call flow has 4 steps:**

1. **Define** — write a JSON schema (function declaration) describing the tool's name, parameters, and types.
2. **Send** — pass `tools=[...]` inside `GenerateContentConfig` alongside your user message.
3. **Execute** — if the model returns a `function_call` part, run your real code.
4. **Return** — send the result back as a `FunctionResponse` (with the `id` field for Gemini 3+) to get the final natural-language answer.

---

## ⚡ Automatic vs. Manual mode

| Mode       | How                                                         | When to use                             |
| ---------- | ----------------------------------------------------------- | --------------------------------------- |
| **Auto**   | Pass real Python functions as tools; SDK handles everything | Prototyping, simple agents              |
| **Manual** | Handle `function_call` parts yourself                       | Production, need control over execution |

Python supports automatic tool calling by passing in the `ClientSession` into the tools parameters. If you want to disable it, provide `automatic_function_calling` with `disabled=True`.

---

## 🛠️ Built-in Tools (no function declarations needed)

The Gemini API also supports built-in tools including: **Code execution** (lets the model write and run Python code), **URL context** (grounds responses in specific web page URLs), **File search** (upload files and ground responses using semantic search), **Google Maps** (grounds responses in location data), and **Computer use** (lets the model interact with a virtual screen, keyboard, and mouse).

---

## 🔗 Key Links

- **Official docs:** https://ai.google.dev/gemini-api/docs/function-calling
- **Tools overview:** https://ai.google.dev/gemini-api/docs/tools
- **Cookbook / examples:** https://github.com/google-gemini/cookbook
- **Get API key:** https://aistudio.google.com/apikey

The current flagship models to use are **`gemini-3.5-flash`** (fast/cheap) and **`gemini-3.1-pro-preview`** (most capable). Both fully support function calling.

```
"""
Google Gemini API – Function Calling (Tool Use)
SDK: google-genai  (pip install google-genai)
Model: gemini-3.5-flash  (latest, May 2026)
Docs: https://ai.google.dev/gemini-api/docs/function-calling
"""

import os
import json
from google import genai
from google.genai import types

# ── 1. Client setup ────────────────────────────────────────────────────────
client = genai.Client()  # reads GEMINI_API_KEY from env automatically

# ── 2. Define your function declarations (tool schema) ─────────────────────
get_weather_fn = {
    "name": "get_weather",
    "description": "Returns current weather for a given city.",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name, e.g. 'Wrocław'",
            },
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit.",
            },
        },
        "required": ["city"],
    },
}

schedule_meeting_fn = {
    "name": "schedule_meeting",
    "description": "Schedules a meeting with specified attendees.",
    "parameters": {
        "type": "object",
        "properties": {
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendees.",
            },
            "date":  {"type": "string", "description": "ISO date, e.g. '2025-07-29'"},
            "time":  {"type": "string", "description": "Time, e.g. '15:00'"},
            "topic": {"type": "string", "description": "Meeting subject."},
        },
        "required": ["attendees", "date", "time", "topic"],
    },
}

# ── 3. Mock implementations (replace with real logic) ──────────────────────
def get_weather(city: str, unit: str = "celsius") -> dict:
    return {"city": city, "temp": 18, "unit": unit, "condition": "Partly cloudy"}

def schedule_meeting(attendees: list, date: str, time: str, topic: str) -> dict:
    return {"status": "scheduled", "attendees": attendees, "date": date,
            "time": time, "topic": topic}

FUNCTION_MAP = {
    "get_weather": get_weather,
    "schedule_meeting": schedule_meeting,
}

# ── 4. Configure tools ─────────────────────────────────────────────────────
tools = types.Tool(function_declarations=[get_weather_fn, schedule_meeting_fn])
config = types.GenerateContentConfig(tools=[tools])

# ── 5. Single-turn: detect & execute one function call ─────────────────────
def run_single_turn(user_message: str):
    print(f"\n[User] {user_message}")

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=user_message,
        config=config,
    )

    part = response.candidates[0].content.parts[0]

    if part.function_call:
        fc = part.function_call
        print(f"[Model → tool] {fc.name}({fc.args})  id={fc.id}")

        # Execute the real function
        result = FUNCTION_MAP[fc.name](**fc.args)
        print(f"[Tool result] {result}")

        # Return result back to model to get final natural-language answer
        follow_up = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[
                types.Content(role="user", parts=[types.Part(text=user_message)]),
                types.Content(role="model", parts=[types.Part(function_call=fc)]),
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=fc.id,          # ← required for Gemini 3+
                                name=fc.name,
                                response=result,
                            )
                        )
                    ],
                ),
            ],
            config=config,
        )
        print(f"[Final answer] {follow_up.text}")
    else:
        print(f"[Answer] {response.text}")


# ── 6. Automatic multi-turn with agentic loop ──────────────────────────────
def get_weather_auto(city: str, unit: str = "celsius") -> dict:
    """Same impl – Python SDK calls this automatically when auto mode is on."""
    return {"city": city, "temp": 18, "unit": unit, "condition": "Partly cloudy"}

def run_auto_turn(user_message: str):
    """
    The Python SDK supports automatic function calling.
    Just pass your real Python functions directly as tools.
    The SDK handles schema extraction + execution loop automatically.
    """
    print(f"\n[Auto mode] {user_message}")

    auto_config = types.GenerateContentConfig(tools=[get_weather_auto])
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=user_message,
        config=auto_config,
    )
    print(f"[Answer] {response.text}")


# ── 7. Built-in tools (no custom code needed) ──────────────────────────────
def run_with_google_search(user_message: str):
    search_config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=user_message,
        config=search_config,
    )
    print(f"[Search answer] {response.text}")


# ── Demo ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_single_turn("What's the weather in Wrocław in Celsius?")
    run_single_turn("Schedule a meeting with Anna and Piotr on 2025-08-01 at 10:00 about the sprint review.")
    run_auto_turn("What's the weather in Kraków?")
    run_with_google_search("What is the latest version of Python?")
```
