"""Local MCP server for cdx-tools (stdio). Start it with `bash scripts/cdx mcp`.

Runs natively on the user's machine, so it can use their Python/RDKit, reach PubChem and open
files in ChemDraw - none of which a sandboxed VM can do. Every drawing result also carries an
RDKit preview image rendered from the saved file, so Claude can check what it drew.
"""

import base64
import io
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

import cdx_tools  # noqa: E402
from check_env import check  # noqa: E402
from tool_schemas import TOOLS, run_tool  # noqa: E402

INSTRUCTIONS = """Native ChemDraw (.cdxml) drawing and reading.
Pair with the chem-tools server: identify compounds with chem-tools get_compound_info first, check the
returned name is what the user meant, then draw from its SMILES with {"structure", "name", "label"}.
Each drawing result includes an RDKit preview of the structures in the saved file - look at it and
fix mistakes before reporting. Give the user the file path; offer open_in_chemdraw if ChemDraw is
installed. If cdx_system_check reports ready=false, tell the user the problems instead of
hand-building structures."""

EXTRA_TOOLS = [
    {
        "name": "open_in_chemdraw",
        "description": "Open a .cdxml/.cdx file written by these tools in ChemDraw on this computer "
                       "(macOS). Only use when the user wants to see the file.",
        "input_schema": {"type": "object", "additionalProperties": False, "required": ["path"],
                         "properties": {"path": {"type": "string", "description": "Path returned by a drawing tool."}}},
    },
    {
        "name": "cdx_system_check",
        "description": "Check Python, RDKit, PubChem access, the chem-tools companion and ChemDraw. "
                       "Run once before the first drawing if anything fails.",
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
]


def _open_in_chemdraw(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    allowed = [cdx_tools.EXPORT_DIR.resolve(), cdx_tools.WORKDIR]
    if p.suffix.lower() not in (".cdxml", ".cdx") or not p.is_file():
        raise ValueError(f"{path} is not an existing .cdxml/.cdx file.")
    if not any(p.is_relative_to(a) for a in allowed):
        raise ValueError(f"{path} is outside the export and working directories.")
    if platform.system() != "Darwin":
        raise ValueError("open_in_chemdraw is only implemented for macOS.")
    subprocess.run(["open", str(p)], check=True, timeout=30)
    return {"opened": str(p)}


def _preview(result: dict) -> list:
    """RDKit grid of the structures actually stored in each written file."""
    from rdkit import Chem
    from rdkit.Chem import Draw, rdMolDescriptors

    paths = [result["path"]] if result.get("path") else list(result.get("paths", []))[:4]
    images = []
    for path in paths:
        with cdx_tools._quiet_stderr():
            mols = [m for m in Chem.MolsFromCDXMLFile(path) if m is not None]
        if not mols:
            continue
        img = Draw.MolsToGridImage(mols[:24], molsPerRow=min(4, len(mols)), subImgSize=(260, 200),
                                   legends=[rdMolDescriptors.CalcMolFormula(m) for m in mols[:24]])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images.append(types.TextContent(
            type="text", text=f"Preview of {Path(path).name}: structures as stored in the file, rendered by "
                              "RDKit (ChemDraw's layout, captions and arrows are not shown)."))
        images.append(types.ImageContent(type="image", mime_type="image/png",
                                         data=base64.b64encode(buf.getvalue()).decode()))
    return images


def _call(name: str, args: dict) -> tuple[str, bool, list]:
    if name == "open_in_chemdraw":
        try:
            return json.dumps(_open_in_chemdraw(**args)), False, []
        except (ValueError, TypeError, subprocess.SubprocessError) as e:
            return json.dumps({"error": str(e)}), True, []
    if name == "cdx_system_check":
        report = check()
        return json.dumps(report), not report["ready"], []
    output, is_error = run_tool(name, args)
    extra = []
    if not is_error and name != "read_chemdraw":
        try:
            extra = _preview(json.loads(output))
        except Exception as e:  # a preview failure must not hide a successful drawing
            extra = [types.TextContent(type="text", text=f"(preview unavailable: {e})")]
    return output, is_error, extra


async def list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[
        types.Tool(name=t["name"], description=t["description"], input_schema=t["input_schema"])
        for t in TOOLS + EXTRA_TOOLS
    ])


async def call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    # Tools make blocking HTTP / RDKit calls; keep them off the event loop
    output, is_error, extra = await anyio.to_thread.run_sync(_call, params.name, params.arguments or {})
    return types.CallToolResult(content=[types.TextContent(type="text", text=output), *extra],
                                is_error=is_error)


server = Server("cdx-tools", version="1.0.0", instructions=INSTRUCTIONS,
                on_list_tools=list_tools, on_call_tool=call_tool)


def serve():
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    anyio.run(main)


if __name__ == "__main__":
    serve()
