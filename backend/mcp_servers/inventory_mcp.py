from backend.db.client import get_part, check_compatibility, search_by_model, get_part_by_mpn, find_replacement_parts


# Tool definitions
# These are the schemas the model reads to decide when and how to call each tool.
# Writing descriptions as decision rules, not API docs so model uses them
# to decide whether to call the tool, not to understand the implementation.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_part",
            "description": (
                "Look up a single part by its PS number (e.g. PS11752778). "
                "Call this whenever the user mentions a specific PS part number - but NOT when they want to replace it. For replace intent use find_alternatives instead."
                "Returns full details: name, price, stock status, brand, "
                "install difficulty, install time, video URL, and product page link. "
                "Do NOT call this as a follow-up to diagnose_symptom — "
                "diagnose_symptom already returns full part details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "part_id": {
                        "type": "string",
                        "description": "PS number exactly as stated, e.g. PS11752778"
                    }
                },
                "required": ["part_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_by_mpn",
            "description": (
                "Look up parts by manufacturer part number (MPN) when the user "
                "provides a non-PS number like WPW10321304 or W10321304. "
                "Call this when the identifier does NOT start with 'PS'. "
                "May return multiple parts if the MPN is shared across brands — "
                "present all results and let the user confirm the right one. "
                "If no results found, ask the user for their model number instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mpn": {
                        "type": "string",
                        "description": "Manufacturer part number exactly as stated, e.g. WPW10321304"
                    }
                },
                "required": ["mpn"]
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "find_alternatives",
            "description": (
                "Find alternative parts to a known PS number. Call this when "
                "the user wants to REPLACE a specific part they've already "
                "identified — e.g. 'I need to replace PS11738120', 'what can "
                "I use instead of PS#####'. Returns the original part plus "
                "alternatives that fix the same symptoms. Do NOT call this "
                "for install questions — use get_part for those."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "part_id": {"type": "string", "description": "PS number"}
                },
                "required": ["part_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_compatibility",
            "description": (
                "Check whether a specific part is compatible with a specific appliance "
                "model number. Call this for any compatibility question — never guess. "
                "Returns compatible: true/false with the part name and product URL."
            ),
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_model",
            "description": (
                "Find parts compatible with an appliance model number when the user "
                "mentions a model but no specific part. "
                "Returns up to 10 matching parts sorted by customer rating."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model_number": {
                        "type": "string",
                        "description": "Appliance model number, e.g. WDT780SAEM1"
                    }
                },
                "required": ["model_number"]
            }
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
        case "get_by_mpn":
            return _get_by_mpn(inputs["mpn"])
        case "find_alternatives":
            # From what I have observed, the dataset isn't dense enough to acutally have any parts alternatives despite replace_parts populated columns
            return _find_alternatives(inputs["part_id"])
        case "check_compatibility":
            return _check_compatibility(inputs["part_id"], inputs["model_number"])
        case "search_by_model":
            return _search_by_model(inputs["model_number"])
        case _:
            return {"error": f"inventory_mcp does not own tool: {tool_name}"}


# Private DB functions

def _get_part(part_id: str) -> dict:
    result = get_part(part_id)
    if not result:
        return {"error": f"No part found with PS number {part_id}"}
    return result

def _get_by_mpn(mpn: str) -> dict:
    results = get_part_by_mpn(mpn)
    if not results:
        return {"error": f"No parts found for {mpn}. This may not be a PartSelect-stocked part — try searching by model number instead."}
    return {"results": results, "note": "supersedes_lookup" if ... else "direct_match"}

def _find_alternatives(part_id: str) -> dict:
    original = get_part(part_id)
    if not original:
        return {"error": f"No part found with PS number {part_id}"}
 
    alternatives = find_replacement_parts(
        part_id=part_id,
        mpn_id=original.get("mpn_id"),
        replace_parts_str=original.get("replace_parts") or "",
    )
    return {"original": original, "alternatives": alternatives}
 

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