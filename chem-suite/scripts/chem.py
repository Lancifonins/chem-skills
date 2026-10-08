#!/usr/bin/env python3
"""Command-line entry point for the chem-suite skill (usually called via the `chem` launcher).

    chem version                              # skill name and version
    chem report                               # Markdown bug report: versions, system check, recent failures
    chem check                                # system check (Python, RDKit, PubChem/ChEMBL, ChemDraw)
    chem mcp                                  # run as a local MCP server (stdio)
    chem list                                 # tool names + descriptions
    chem schema get_compound_info             # JSON schema for one tool
    chem get_compound_info '{"identifier": "caffeine", "include": ["safety"]}'
    chem get_compound_info caffeine           # shorthand for the first required arg

Prints the result as JSON on stdout; exits 1 on a tool error.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))



def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "check":  # before importing RDKit, so a missing install is reported, not raised
        from check_env import check
        report = check()
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 1
    if argv[0] == "version":
        from diagnostics import SKILL_NAME, VERSION
        print(json.dumps({"skill": SKILL_NAME, "version": VERSION}))
        return 0
    if argv[0] == "report":
        from diagnostics import report
        print(report())
        return 0
    if argv[0] == "mcp":
        from mcp_server import serve
        serve()
        return 0

    from tool_schemas import TOOLS, run_tool

    by_name = {t["name"]: t for t in TOOLS}

    if argv[0] == "list":
        for t in TOOLS:
            print(f"{t['name']}: {t['description']}\n")
        return 0
    if argv[0] == "schema":
        targets = [by_name[n] for n in argv[1:] if n in by_name] or TOOLS
        print(json.dumps([t["input_schema"] | {"name": t["name"]} for t in targets], indent=2))
        return 0

    name, rest = argv[0], argv[1:]
    if name not in by_name:
        print(json.dumps({"error": f"Unknown tool '{name}'. Run 'python chem.py list'."}))
        return 1
    raw = " ".join(rest).strip()
    if raw.startswith("{"):
        try:
            tool_input = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON input: {e}"}))
            return 1
    else:
        first = by_name[name]["input_schema"]["required"][0]
        tool_input = {first: raw} if raw else {}

    result, is_error = run_tool(name, tool_input)
    print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    return 1 if is_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
