from backend.db.client import get_part, check_compatibility, search_by_model


# Tool definitions 
# These are the schemas Claude reads to decide when and how to call each tool.
# Write descriptions as decision rules, not API docs — the model uses them
# to decide whether to call the tool, not to understand the implementation.

TOOLS = [
    {
        "name": "get_part",
        "description": (
            "Look up a single part by its PS number (e.g. PS11752778). "
            "Call this whenever the user mentions a specific PS part number. "
            "Returns full details: name, price, stock status, brand, "
            "install difficulty, install time, video URL, and product page link. "
            "Do NOT call this as a follow-up to diagnose_symptom — "
            "diagnose_symptom already returns full part details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_id": {
                    "type": "string",
                    "description": "PS number exactly as stated, e.g. PS11752778"
                }
            },
            "required": ["part_id"]
        }
    },
    {
        "name": "check_compatibility",
        "description": (
            "Check whether a specific part is compatible with a specific appliance "
            "model number. Call this for any compatibility question — never guess. "
            "Returns compatible: true/false with the part name and product URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_id": {
                    "type": "string",
                    "description": "PS number of the part to check"
                },
                "model_number": {
                    "type": "string",
                    "description": "Appliance model number, e.g. WDT780SAEM1"
                }
            },
            "required": ["part_id", "model_number"]
        }
    },
    {
        "name": "search_by_model",
        "description": (
            "Find parts compatible with an appliance model number when the user "
            "mentions a model but no specific part. "
            "Returns up to 10 matching parts sorted by customer rating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_number": {
                    "type": "string",
                    "description": "Appliance model number, e.g. WDT780SAEM1"
                }
            },
            "required": ["model_number"]
        }
    },
]


# Execution 

def execute(tool_name: str, inputs: dict) -> dict:
    """
    Execute an inventory tool by name.
    Called by the loop's MCP registry — never called directly by the agent.
    Returns a dict that gets JSON-serialised into the tool_result message.
    """
    match tool_name:
        case "get_part":
            return _get_part(inputs["part_id"])
        case "check_compatibility":
            return _check_compatibility(inputs["part_id"], inputs["model_number"])
        case "search_by_model":
            return _search_by_model(inputs["model_number"])
        case _:
            return {"error": f"inventory_mcp does not own tool: {tool_name}"}


# ── Private DB functions ──────────────────────────────────────────────────────

def _get_part(part_id: str) -> dict:
    result = get_part(part_id)
    if not result:
        return {"error": f"No part found with PS number {part_id}"}
    return result


def _check_compatibility(part_id: str, model_number: str) -> dict:
    result = check_compatibility(part_id, model_number)
    if not result:
        return {"error": f"Could not check compatibility for {part_id} / {model_number}"}
    return result


def _search_by_model(model_number: str) -> dict:
    results = search_by_model(model_number)
    if not results:
        return {"error": f"No parts found for model {model_number}"}
    return {"results": results}