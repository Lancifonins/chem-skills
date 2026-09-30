---
name: chem-tools
description: Chemistry lookup and structure toolkit backed by PubChem, ChEMBL and RDKit. Resolves compound names, CAS numbers, SMILES, InChIKeys and PubChem CIDs to each other, and returns molecular weight, formula, GHS hazards, experimental density/boiling point/melting point/flash point/solubility/pKa, and vendor availability. Also runs substructure (SMARTS) and bioactive-similarity searches, computes RDKit descriptors and Lipinski rules, reads SDF/MOL/CDXML files, and writes ChemDraw-ready SDF, reaction (.rxn) files and labelled structure images. Use this whenever a task names a specific chemical or reagent, asks for a CAS number, molecular weight or hazard, needs a mass-to-volume conversion, involves a structure drawing or reaction scheme, or asks to find compounds of a class - even if the user does not mention PubChem or tools, because recalled CAS numbers, masses and hazards are often wrong.
compatibility: Needs Python 3.10+ and internet access to pubchem.ncbi.nlm.nih.gov and www.ebi.ac.uk. RDKit is installed automatically on first use (via uv, or into a private venv in ~/.cache/chem-skills), which needs PyPI access once. In the Claude desktop app, run it as a local MCP server instead (see references/mcp-setup.md).
license: MIT (see LICENSE in https://github.com/Lancifonins/chem-skills)
metadata:
  version: "1.0.0"
---

# chem-tools

**If `get_compound_info` and the other tools below are already available as MCP tools** (the
chem-tools MCP server, typical in the Claude desktop app), call them directly and skip the
launcher. They are the same tools running natively on the user's machine.

Otherwise every tool runs through one launcher. Always call it with `bash`, because the executable
bit is often lost when a skill is installed. Run it from the user's working directory: output files
go to `./exports` there and input paths resolve from there.

```bash
bash <skill-dir>/scripts/chem check                   # system check - run first
bash <skill-dir>/scripts/chem <tool> '<json input>'
bash <skill-dir>/scripts/chem <tool> <value>          # shorthand: fills the first required field
bash <skill-dir>/scripts/chem list                    # all tools with descriptions
bash <skill-dir>/scripts/chem schema <tool>           # exact JSON input schema
```

The output is JSON on stdout. Exit code 1 means it contains `{"error": ...}`, so read the message
and adjust rather than retrying blindly.

## Step 0: system check (once per session)

Run `check` before the first lookup. The launcher finds a Python 3.10+ with RDKit and installs it
if missing, using uv or a private venv in `~/.cache/chem-skills` (shared with cdx-tools). This
never modifies the user's own environments. A first install takes about a minute; tell the user
rather than going quiet. In the report:
- `ready: false`: RDKit or Python is unusable. See "When the tools can't run" below.
- `network.pubchem` / `network.chembl` false: lookups and searches will fail. Only
  `calculate_properties` and the file tools work offline, from SMILES.
- `cdx_tools`: whether the companion ChemDraw skill is available for drawing results.

## When the tools can't run

Sandboxed workspaces (cloud sandboxes, agent VMs) sometimes block PyPI or PubChem. If `check` is not
ready or lookups fail with network errors:
- **Don't fill in the gaps from memory.** CAS numbers, masses and hazard codes recalled without a
  lookup are exactly the errors this skill exists to prevent. If the user still wants an answer,
  label every such value clearly as unverified.
- Tell the user what failed (quote `problems` / `warnings`) and the fixes: run the task in Claude
  Code on their own computer; register the MCP server in the Claude desktop app
  (`references/mcp-setup.md`); or have an admin allow `pypi.org`, `files.pythonhosted.org`,
  `pubchem.ncbi.nlm.nih.gov` and `www.ebi.ac.uk`.

## Tools

| Tool | Use it for |
|---|---|
| `get_compound_info` | Identity (name, CAS, CID, formula, MW, SMILES, InChIKey), plus optional `include` sections: `safety`, `physical`, `vendors` |
| `search_substructure` | PubChem compounds containing a SMILES or SMARTS fragment |
| `search_similar_bioactives` | ChEMBL drugs/bioactives similar to a compound |
| `calculate_properties` | Offline RDKit descriptors (logP, TPSA, HBD/HBA, Lipinski) |
| `read_structure_file` | Parse .sdf / .mol / .cdxml / .smi files |
| `export_structures` | SDF for ChemDraw: one record each, or one side-by-side canvas |
| `draw_structures_image` | Labelled PNG/SVG grid (legend: index / name / cas / formula) |
| `export_reaction` | .rxn scheme with a real arrow and reagents above it, plus a PNG preview |
| `image_to_structure` | DECIMER image recognition (optional dependency) |

Any `identifier` field accepts a name, CAS number, SMILES, InChIKey or CID. For every parameter
and output field, read `references/tools.md`. For ready-made SMARTS for compound classes, read
`references/smarts.md`.

## How to use them well

**Look things up instead of recalling them.** CAS numbers, molecular weights and hazard codes
from memory are frequently subtly wrong, and in a lab that matters. CAS numbers returned here are
check-digit validated.

**Ask only for the sections you need.** `get_compound_info` always returns identity. Each
`include` section costs extra requests, so "what's the CAS of X" needs nothing extra, while
"I'm about to use X" warrants `["safety"]`. For several compounds, run one call per compound.

**Check the resolved name.** Identifiers are auto-detected: a space-free string that parses as
SMILES is treated as SMILES (`CO` is methanol), and PubChem names are case-insensitive (the name
`CO` is cobalt). If the returned `name` isn't what the user meant, retry with `identifier_type`
set explicitly or use a more specific name.

**Report safety data honestly.** GHS lines are aggregated from many depositors, and the percentage
is the share reporting that hazard. Lead with the signal word and the high-share H-statements, and
point the user to the supplier SDS as the authority.

**Show your work on conversions.** For mass ⇄ volume, fetch `physical` with
`"properties": ["density"]`, pick a value near room temperature, state its conditions, and show
the arithmetic. Molarity and equivalents use `molecular_weight` from identity.

**Finding compounds of a class** (e.g. "six amino acids for a figure"): use `search_substructure`
with a SMARTS from `references/smarts.md`, pick sensible hits, then pass their names to
`draw_structures_image` or `export_structures`. Tell the user the hits come in PubChem's order.

**Structure images from the user:** if you can see the image, read the structure yourself and pass
the SMILES on. `image_to_structure` is only for image files you cannot view, and needs DECIMER.

**Files:** tell the user the full output path. Change the locations with the `CHEM_EXPORT_DIR`
(outputs) and `CHEM_WORKDIR` (allowed input root) environment variables. Paths outside the input
root are refused.

## Examples

```bash
bash scripts/chem get_compound_info 64-17-5
bash scripts/chem get_compound_info '{"identifier": "dichloromethane", "include": ["safety"]}'
bash scripts/chem get_compound_info '{"identifier": "THF", "include": ["physical"], "properties": ["density", "boiling_point"]}'
bash scripts/chem search_substructure '{"query": "c[OX2H]", "query_type": "smarts", "max_results": 8}'
bash scripts/chem draw_structures_image '{"compounds": ["glycine", "L-alanine", "L-serine"], "legend": "index_name_cas", "columns": 3}'
bash scripts/chem export_reaction '{"reactants": ["benzene", "nitric acid"], "products": ["nitrobenzene"], "reagents": ["sulfuric acid"]}'
```

## Reporting problems

Failed tool calls are logged locally (see `error_log` in `check`). If a tool returns an error that
looks like a bug rather than bad input (an exception name like `KeyError:` or `Bad arguments`, or
output that is plainly wrong), run `bash <skill-dir>/scripts/chem report`. Show the user the
Markdown it prints: it has the skill version, the environment check and the recent failures with
tracebacks, ready to send to the skill's author. Set `CHEM_SKILLS_DEBUG=1` to log successful calls
too. `bash <skill-dir>/scripts/chem version` prints the installed version.
