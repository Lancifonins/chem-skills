"""Tool registry for chem-suite: every chem-tools and cdx-tools tool in one list, one dispatcher.

chem_schemas.py and cdx_schemas.py are the two skills' own tool_schemas.py files, copied in
unchanged by tools/assemble_suite.py, so the schemas are maintained in one place only.
"""

import json
import traceback

import cdx_schemas
import chem_schemas
from diagnostics import log_call
from pubchem import ToolError

TOOLS = chem_schemas.TOOLS + cdx_schemas.TOOLS
FUNCTIONS = {**chem_schemas.FUNCTIONS, **cdx_schemas.FUNCTIONS}
if len(FUNCTIONS) != len(TOOLS):
    raise RuntimeError("chem-tools and cdx-tools define a tool with the same name")
DRAWING_TOOLS = set(cdx_schemas.FUNCTIONS) - {"read_chemdraw"}


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a tool call. Returns (JSON string, is_error). Failures are logged for `report`."""
    tb = None
    fn = FUNCTIONS.get(name)
    if fn is None:
        result, is_error = {"error": f"Unknown tool '{name}'."}, True
    else:
        try:
            result, is_error = fn(**tool_input), False
        except ToolError as e:
            result, is_error = {"error": str(e)}, True
        except TypeError as e:
            result, is_error = {"error": f"Bad arguments for {name}: {e}"}, True
            tb = traceback.format_exc()
        except Exception as e:  # keep callers alive on unexpected failures; the log keeps the traceback
            result, is_error = {"error": f"{type(e).__name__}: {e}"}, True
            tb = traceback.format_exc()
    log_call(name, tool_input, result, is_error, tb)
    return json.dumps(result, ensure_ascii=False, default=str), is_error
