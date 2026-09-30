"""Tool registry: JSON-Schema definitions for the ChemDraw tools, plus the dispatcher cdx.py uses."""

import json
import traceback

import cdx_tools as ct
from diagnostics import log_call
from pubchem import ToolError

_COMPOUND = {
    "anyOf": [
        {"type": "string", "description": "Name, CAS number or SMILES."},
        {
            "type": "object",
            "properties": {
                "structure": {"type": "string", "description": "Name, CAS number or SMILES."},
                "label": {"type": "string", "description": "Custom compound number shown in bold, e.g. '3a'."},
                "name": {"type": "string", "description": "Caption text to show instead of the input."},
            },
            "required": ["structure"],
            "additionalProperties": False,
        },
    ]
}
_COMPOUNDS = {"type": "array", "items": _COMPOUND, "minItems": 1}
_CAPTION = {
    "type": "string",
    "description": "Caption lines under each structure: any of 'number', 'name', 'cas', 'formula', 'mw' "
                   "joined by '_' (e.g. 'number_name'), or 'none'.",
}
_FILENAME = {"type": "string", "description": "Output file stem; '.cdxml' is added."}


def _tool(name, description, properties, required=()):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties,
                             "required": list(required), "additionalProperties": False}}


TOOLS = [
    _tool(
        "draw_structures",
        "Draw one or more compounds into a native, editable ChemDraw .cdxml file, laid out as a grid or "
        "a single row, with captions under each structure (bold compound numbers, names, CAS, formula, MW). "
        "Stereochemistry is drawn with wedges. Use separate_files for one file per compound.",
        {
            "compounds": _COMPOUNDS,
            "layout": {"type": "string", "enum": ["grid", "row"]},
            "columns": {"type": "integer", "minimum": 1, "maximum": 12, "description": "Grid columns (default 4)."},
            "caption": _CAPTION,
            "number_start": {"type": "integer", "minimum": 1, "description": "First automatic compound number."},
            "filename": _FILENAME,
            "separate_files": {"type": "boolean"},
        },
        ["compounds"],
    ),
    _tool(
        "draw_reaction",
        "Draw a reaction scheme into a native ChemDraw .cdxml file: structures joined by '+', a real reaction "
        "arrow with reagents above it and conditions/yield below, compound numbers underneath, and ChemDraw "
        "reaction-step metadata. Single step: reactants + products (+ reagents, conditions, yield_text). "
        "Linear multi-step route: reactants (starting materials) + steps, each step's products becoming the "
        "next step's starting point.",
        {
            "reactants": _COMPOUNDS,
            "products": _COMPOUNDS,
            "reagents": {"type": "array", "items": _COMPOUND,
                         "description": "Written above the arrow, as text (default) or structures."},
            "conditions": {"type": "string",
                           "description": "Below the arrow; ';' or newline starts a new line, e.g. 'THF, 0 °C; 2 h'."},
            "yield_text": {"type": "string", "description": "e.g. '85%'; shown under the conditions."},
            "steps": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "reagents": {"type": "array", "items": _COMPOUND},
                        "conditions": {"type": "string"},
                        "yield": {"type": "string"},
                        "products": _COMPOUNDS,
                    },
                    "required": ["products"],
                    "additionalProperties": False,
                },
                "description": "Multi-step route. When given, 'products'/'reagents'/'conditions'/'yield_text' are ignored.",
            },
            "caption": _CAPTION,
            "number_start": {"type": "integer", "minimum": 1},
            "reagents_as": {"type": "string", "enum": ["text", "structures"],
                            "description": "'text' writes reagent names (formulas get subscripts); 'structures' draws them."},
            "filename": _FILENAME,
        },
        ["reactants"],
    ),
    _tool(
        "convert_to_chemdraw",
        "Convert a structure file into a ChemDraw .cdxml document: .sdf/.mol/.smi become a captioned grid "
        "(SDF titles and SMILES-file names are used as captions); .rxn becomes a reaction scheme with an arrow.",
        {
            "path": {"type": "string", "description": "Input file, relative to the working directory."},
            "layout": {"type": "string", "enum": ["grid", "row"]},
            "columns": {"type": "integer", "minimum": 1, "maximum": 12},
            "caption": _CAPTION,
            "filename": _FILENAME,
        },
        ["path"],
    ),
    _tool(
        "read_chemdraw",
        "Read a ChemDraw .cdxml or binary .cdx file: returns every structure (SMILES, formula, MW, InChIKey), "
        "reaction SMILES for drawn reaction steps, and free text such as captions and conditions (.cdxml only).",
        {
            "path": {"type": "string", "description": "File relative to the working directory."},
            "max_structures": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
        ["path"],
    ),
]

FUNCTIONS = {t["name"]: getattr(ct, t["name"]) for t in TOOLS}


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
