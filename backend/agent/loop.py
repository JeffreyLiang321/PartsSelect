"""
Agentic loop has 1 job: run the model conversation loop.
"""

import json
import time
from openai import OpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL, MAX_ITERATIONS
from backend.agent.system_prompt import SYSTEM_PROMPT
from backend.mcp_servers import inventory_mcp, rag_mcp

client = OpenAI(api_key=OPENAI_API_KEY)

# MCP registry
TOOLS = inventory_mcp.TOOLS + rag_mcp.TOOLS

_MCP_REGISTRY: dict = {
    tool["function"]["name"]: server
    for server in [inventory_mcp, rag_mcp]
    for tool in server.TOOLS
}

# Tools whose results may contain part records
_PART_TOOLS = {"get_part", "get_by_mpn", "check_compatibility", "search_by_model", "diagnose_symptom"}


# Agentic loop

def run_agent(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Core agentic loop.

    Takes full conversation history, returns (reply_text, collected_parts).
    collected_parts is a deduplicated list of full part dicts fetched during
    this turn — the API includes these so the frontend can render rich cards.

    Termination: check for absence of tool_calls on the assistant message.
    Relying on finish_reason alone would misfire on 'length' (max_tokens hit).

    History safety: copy the message list so callers don't see in-flight
    tool messages appended during this turn.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
    collected_parts: list[dict] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_completion_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        msg = response.choices[0].message

        # Termination check: no tool_calls → model is done
        if not msg.tool_calls:
            return msg.content or "", _dedupe_parts(collected_parts)

        # Append the assistant turn (with its tool_calls) before tool results
        messages.append(msg)

        # Execute all tool calls in this response
        for tool_call in msg.tool_calls:
            inputs = json.loads(tool_call.function.arguments)
            result = _execute_tool(tool_call.function.name, inputs, iteration)
            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      json.dumps(result),
            })
            if tool_call.function.name in _PART_TOOLS:
                _collect_parts(result, collected_parts)

    return (
        "I wasn't able to complete your request. Please try rephrasing or ask again.",
        _dedupe_parts(collected_parts),
    )


# Part collection helpers

def _collect_parts(result: dict, collected: list[dict]) -> None:
    """Append part dicts from a tool result into the collected list."""
    if "error" in result or not isinstance(result, dict):
        return
    if "part_id" in result:
        collected.append(result)
    elif "results" in result:
        for item in result["results"]:
            if isinstance(item, dict) and "part_id" in item:
                collected.append(item)


def _dedupe_parts(parts: list[dict]) -> list[dict]:
    """Return parts with duplicates removed, keeping first occurrence per part_id."""
    seen: set[str] = set()
    out: list[dict] = []
    for p in parts:
        pid = p.get("part_id")
        if pid and pid not in seen:
            seen.add(pid)
            out.append(p)
    return out


# Tool execution

def _execute_tool(name: str, inputs: dict, iteration: int) -> dict:
    server = _MCP_REGISTRY.get(name)
    if not server:
        result = {"error": f"Unknown tool: {name}"}
        _log_tool(iteration, name, inputs, result, latency_ms=0)
        return result

    t0 = time.perf_counter()
    try:
        result = server.execute(name, inputs)
    except Exception as e:
        result = {"error": f"Tool execution failed: {str(e)}"}
    latency_ms = (time.perf_counter() - t0) * 1000

    _log_tool(iteration, name, inputs, result, latency_ms)
    return result


def _log_tool(iteration: int, name: str, inputs: dict, result: dict, latency_ms: float):
    inputs_str = json.dumps(inputs)
    result_str = json.dumps(result)
    preview    = result_str[:200] + ("..." if len(result_str) > 200 else "")
    print(
        f"[tool][iter {iteration}] {name}({inputs_str})"
        f"\n         → {preview}"
        f"\n         ({latency_ms:.0f}ms)"
    )
