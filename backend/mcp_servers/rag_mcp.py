from backend.db.vector import semantic_search, search_repair_guide, search_blogs


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "diagnose_symptom",
        "description": (
            "Find parts that fix a described problem using semantic search. "
            "Use this when the user describes a symptom or malfunction — "
            "e.g. 'ice maker not working', 'dishwasher leaking from bottom', "
            "'fridge making loud noise'. "
            "Returns full part details including price, stock, and product URL. "
            "Do NOT call get_part after this — results are already complete."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom": {
                    "type": "string",
                    "description": "Natural language description of the problem"
                },
                "appliance_type": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Must be exactly 'refrigerator' or 'dishwasher'"
                }
            },
            "required": ["symptom", "appliance_type"]
        }
    },
    {
        "name": "search_repair_guide",
        "description": (
            "Find a step-by-step repair guide for an appliance symptom. "
            "Use when the user asks how to fix something, wants repair steps, "
            "or asks about difficulty of a repair. "
            "Returns the symptom, difficulty, repair steps per part, and a video URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom": {
                    "type": "string",
                    "description": "Natural language description of the symptom"
                },
                "appliance_type": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Must be exactly 'refrigerator' or 'dishwasher'"
                }
            },
            "required": ["symptom", "appliance_type"]
        }
    },
    {
        "name": "search_blogs",
        "description": (
            "Find relevant PartSelect blog posts on a topic. "
            "Use when the user asks a how-to or maintenance question that "
            "would be well served by a full article — e.g. 'how do I clean "
            "my dishwasher filter', 'why is my fridge making noise'. "
            "Returns matching blog titles and URLs to share with the user. "
            "Only call this for refrigerator or dishwasher topics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic or question to search blog posts for"
                }
            },
            "required": ["query"]
        }
    },
]


# ── Execution ─────────────────────────────────────────────────────────────────

def execute(tool_name: str, inputs: dict) -> dict:
    """
    Execute a RAG tool by name.
    Called by the loop's MCP registry — never called directly by the agent.
    """
    match tool_name:
        case "diagnose_symptom":
            return _diagnose_symptom(inputs["symptom"], inputs["appliance_type"])
        case "search_repair_guide":
            return _search_repair_guide(inputs["symptom"], inputs["appliance_type"])
        case "search_blogs":
            return _search_blogs(inputs["query"])
        case _:
            return {"error": f"rag_mcp does not own tool: {tool_name}"}


# ── Private functions ─────────────────────────────────────────────────────────

def _diagnose_symptom(symptom: str, appliance_type: str) -> dict:
    if appliance_type not in ("refrigerator", "dishwasher"):
        return {"error": "appliance_type must be 'refrigerator' or 'dishwasher'"}
    results = semantic_search(symptom, appliance_type)
    if not results:
        return {"error": f"No parts found matching: {symptom}"}
    return {"results": results}


def _search_repair_guide(symptom: str, appliance_type: str) -> dict:
    if appliance_type not in ("refrigerator", "dishwasher"):
        return {"error": "appliance_type must be 'refrigerator' or 'dishwasher'"}
    result = search_repair_guide(symptom, appliance_type)
    if not result:
        return {"error": f"No repair guide found for: {symptom}"}
    return result


def _search_blogs(query: str) -> dict:
    results = search_blogs(query)
    if not results:
        return {"error": f"No blog posts found for: {query}"}
    return {"results": results}