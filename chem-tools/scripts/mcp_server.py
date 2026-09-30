"""Local MCP server for chem-tools (stdio). Start it with `bash scripts/chem mcp`.

Runs natively on the user's machine, so it can use their Python/RDKit and reach PubChem and
ChEMBL. Structure images written by the tools are returned inline so Claude can see them.
"""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from check_env import check  # noqa: E402
from tool_schemas import TOOLS, run_tool  # noqa: E402

INSTRUCTIONS = """Chemistry information tools backed by PubChem, ChEMBL and RDKit.
Use get_compound_info instead of recalling CAS numbers, masses or hazards, and request only the
`include` sections the question needs. Include 'safety' whenever the user will handle a compound,
and point them to the supplier SDS. If a lookup fails, say so - never fill in CAS numbers, masses
or hazards from memory without labelling them as unverified. For native ChemDraw files, pass the
verified SMILES to the cdx-tools server."""

EXTRA_TOOLS = [{
    "name": "chem_system_check",
    "description": "Check Python, RDKit, PubChem/ChEMBL access and the cdx-tools companion. "
                   "Run when a tool fails with a network or installation error.",
    "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
}]
MAX_INLINE_IMAGE_BYTES = 3_000_000


def _inline_images(result: dict) -> list:
    images = []
    for key in ("path", "image_path"):
        p = Path(str(result.get(key, "")))
        if p.suffix == ".png" and p.is_file() and p.stat().st_size <= MAX_INLINE_IMAGE_BYTES:
            images.append(types.ImageContent(type="image", mime_type="image/png",
                                             data=base64.b64encode(p.read_bytes()).decode()))
    return images


def _call(name: str, args: dict) -> tuple[str, bool, list]:
    if name == "chem_system_check":
        report = check()
        return json.dumps(report), not report["ready"], []
    output, is_error = run_tool(name, args)
    return output, is_error, ([] if is_error else _inline_images(json.loads(output)))


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


server = Server("chem-tools", version="1.0.0", instructions=INSTRUCTIONS,
                on_list_tools=list_tools, on_call_tool=call_tool)


def serve():
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    anyio.run(main)


if __name__ == "__main__":
    serve()
