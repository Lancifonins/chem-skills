"""Tool registry: JSON-Schema definitions for every chem tool, plus the dispatcher chem.py uses.

The schemas follow the Claude tool-definition format, so they can also be passed as `tools=`
to the Claude API if the scripts are ever reused outside the skill.
"""

import json
import traceback

import chem_tools as ct
from diagnostics import log_call
from pubchem import ToolError

_IDENTIFIER = {
    "type": "string",
    "description": "Compound name, CAS number (e.g. '64-17-5'), SMILES, InChIKey, or PubChem CID.",
}
_COMPOUND_LIST = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "description": "Compounds as names, CAS numbers, or SMILES (can be mixed).",
}
_FILENAME = {"type": "string", "description": "Output file stem; the extension is added automatically."}


def _tool(name, description, properties, required=()):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "get_compound_info",
        "Look up a compound in PubChem. Always returns identity: name, IUPAC name, "
        "check-digit-validated CAS number, CID, formula, molecular weight, exact mass, SMILES, "
        "InChIKey, XLogP, TPSA and a PubChem link. Add sections with `include`: 'safety' (GHS "
        "signal word, pictograms, all H-statements with the share of notifiers reporting each, "
        "P-codes), 'physical' (verbatim experimental density, boiling/melting/flash point, "
        "solubility, vapour pressure, refractive index, pKa), 'vendors' (chemical vendors listed "
        "in PubChem with catalogue links; no prices or stock). Request only the sections the "
        "question needs, and use this instead of recalling CAS numbers, masses or hazards.",
        {
            "identifier": _IDENTIFIER,
            "include": {
                "type": "array",
                "items": {"type": "string", "enum": list(ct.SECTIONS)},
                "description": "Extra sections to fetch. Omit for identity only. Use 'safety' whenever "
                               "the user will handle the compound; 'physical' for mass/volume conversions.",
            },
            "identifier_type": {
                "type": "string",
                "enum": ["auto", "name", "cas", "smiles", "inchi", "inchikey", "cid"],
                "description": "Leave as 'auto' unless detection guesses wrong. Auto treats any space-free string RDKit can parse as SMILES ('CO' = methanol).",
            },
            "properties": {
                "type": "array",
                "items": {"type": "string", "enum": list(ct.PHYSICAL_HEADINGS)},
                "description": "Physical properties for the 'physical' section. Defaults to density, boiling, melting and flash point.",
            },
            "max_values": {"type": "integer", "minimum": 1, "maximum": 10,
                           "description": "Max reported values per physical property (default 4)."},
            "max_vendors": {"type": "integer", "minimum": 1, "maximum": 50,
                            "description": "Max vendors listed in the 'vendors' section (default 15)."},
        },
        ["identifier"],
    ),
    _tool(
        "search_substructure",
        "Find PubChem compounds containing a substructure. Accepts SMILES, or SMARTS for "
        "compound classes (e.g. alpha-amino acids: '[NX3;!$(N-C=O)][CX4][CX3](=O)[OX2H1,OX1-]', phenols: "
        "'c[OX2H]'). Returns names, CIDs, formulas and SMILES.",
        {
            "query": {"type": "string", "description": "Substructure as SMILES or SMARTS."},
            "query_type": {"type": "string", "enum": ["smiles", "smarts"]},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            "include_cas": {"type": "boolean",
                            "description": "Also resolve CAS numbers (one extra request per hit; default false)."},
        },
        ["query"],
    ),
    _tool(
        "search_similar_bioactives",
        "Search ChEMBL for bioactive molecules and drugs structurally similar (Tanimoto) to a "
        "compound. Returns ChEMBL IDs, names, similarity, max clinical phase and SMILES.",
        {
            "identifier": _IDENTIFIER,
            "similarity_threshold": {"type": "integer", "minimum": 40, "maximum": 100,
                                     "description": "Minimum similarity percent (default 80)."},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        ["identifier"],
    ),
    _tool(
        "calculate_properties",
        "Compute properties locally with RDKit: formula, MW, exact mass, InChIKey, Crippen logP, "
        "TPSA, H-bond donors/acceptors, rotatable bonds, rings, Fsp3, stereocentres and Lipinski "
        "violations. Works offline for SMILES; use it for drawn/novel structures not in PubChem.",
        {"identifier": _IDENTIFIER},
        ["identifier"],
    ),
    _tool(
        "read_structure_file",
        "Read structures from a local .sdf, .mol, .cdxml or .smi file (path relative to the working "
        "directory) and return SMILES, formula, MW and InChIKey for every structure. Several "
        "drawings on one ChemDraw canvas are returned separately.",
        {
            "path": {"type": "string", "description": "e.g. 'input_files/single_mol_file.sdf'"},
            "max_molecules": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        ["path"],
    ),
    _tool(
        "export_structures",
        "Write compounds to an SDF file that opens in ChemDraw. layout='separate' writes one record "
        "per compound; 'single_canvas' puts them side by side in one drawing.",
        {
            "compounds": _COMPOUND_LIST,
            "filename": _FILENAME,
            "layout": {"type": "string", "enum": ["separate", "single_canvas"]},
        },
        ["compounds"],
    ),
    _tool(
        "draw_structures_image",
        "Render compounds as a labelled grid image (PNG or SVG). Legends can combine index, name, "
        "CAS and formula, e.g. 'index_name_cas'.",
        {
            "compounds": _COMPOUND_LIST,
            "legend": {"type": "string",
                       "description": "Any combination of 'index', 'name', 'cas', 'formula' joined by '_'. Default 'name'."},
            "columns": {"type": "integer", "minimum": 1, "maximum": 10},
            "filename": _FILENAME,
            "image_format": {"type": "string", "enum": ["png", "svg"]},
        },
        ["compounds"],
    ),
    _tool(
        "export_reaction",
        "Write a reaction scheme as an MDL .rxn file (opens in ChemDraw with a reaction arrow; "
        "reagents go above the arrow) plus a PNG preview, and return the reaction SMILES.",
        {
            "reactants": _COMPOUND_LIST,
            "products": _COMPOUND_LIST,
            "reagents": {"type": "array", "items": {"type": "string"},
                         "description": "Catalysts, reagents or solvents shown over the arrow."},
            "filename": _FILENAME,
            "image": {"type": "boolean", "description": "Also write a PNG preview (default true)."},
        },
        ["reactants", "products"],
    ),
    _tool(
        "image_to_structure",
        "Recognise a chemical structure in an image file with DECIMER and look it up in PubChem. "
        "Only needed when the image cannot be sent to Claude directly; requires DECIMER.",
        {
            "image_path": {"type": "string", "description": "Image path relative to the working directory."},
            "lookup": {"type": "boolean", "description": "Also look the structure up in PubChem (default true)."},
        },
        ["image_path"],
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
