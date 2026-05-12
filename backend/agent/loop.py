"""
Agentic loop — thin orchestration only.

One job: run the Claude conversation loop.
It does NOT define tools and does NOT contain DB or search logic.

Tool definitions come from the MCP servers.
Tool execution routes through the MCP registry.
Adding a new tool = edit one MCP server file, zero changes here.
"""

import json
import time
import anthropic

from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_ITERATIONS
from backend.agent.system_prompt import SYSTEM_PROMPT
from backend.mcp_servers import inventory_mcp, rag_mcp

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# MCP registry
# Aggregate tool definitions from all MCP servers.
# Claude receives this flat list and decides which tool to call.
# The registry maps each tool name back to the server that owns it,
# so the loop can route execution without knowing anything about the tools.

TOOLS = inventory_mcp.TOOLS + rag_mcp.TOOLS

_MCP_REGISTRY: dict = {
    tool["name"]: server
    for server in [inventory_mcp, rag_mcp]
    for tool in server.TOOLS
}


# Agentic loop

def run_agent(messages: list[dict]) -> str:
    """
    Core agentic loop.

    Takes full conversation history, returns Claude's final text response.

    Correct termination: check for absence of tool_use blocks in response.content
    rather than relying solely on stop_reason. stop_reason == "max_tokens" would
    fall through to the tool branch with zero tool_use blocks and corrupt history.

    History safety: we copy the message list at the start so callers don't see
    in-flight tool_result messages appended during this turn. Each call to
    run_agent is self-contained.
    """
    messages = list(messages)  # shallow copy — don't mutate caller's list

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        # Termination check: no tool_use blocks → Claude is done
        has_tool_use = any(
            block.type == "tool_use" for block in response.content
        )

        if not has_tool_use:
            # Safely join all text blocks (handles multi-block responses)
            return "".join(
                block.text
                for block in response.content
                if hasattr(block, "text")
            )

        # Execute all tool calls in this response 
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            result = _execute_tool(block.name, block.input, iteration)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     json.dumps(result)
            })

        # Append assistant turn + tool results before next loop iteration
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

    # MAX_ITERATIONS reached without a clean stop
    return "I wasn't able to complete your request. Please try rephrasing or ask again."


# Tool execution 

def _execute_tool(name: str, inputs: dict, iteration: int) -> dict:
    """
    Route a tool call to the MCP server that owns it.

    Logs name, inputs, result (truncated), and latency on every call.
    This is what makes the agent auditable — reviewers and interviewers
    should be able to see exactly what the agent called and what it got back.
    """
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
    """
    Structured tool call log.
    Format: [tool][iter N] name(inputs) → result_preview (Xms)
    Truncated at 200 chars so logs stay scannable in the terminal.
    """
    inputs_str = json.dumps(inputs)
    result_str = json.dumps(result)
    preview    = result_str[:200] + ("..." if len(result_str) > 200 else "")
    print(
        f"[tool][iter {iteration}] {name}({inputs_str})"
        f"\n         → {preview}"
        f"\n         ({latency_ms:.0f}ms)"
    )