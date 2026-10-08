---
name: chem-suite
description: All-in-one chemistry toolkit backed by PubChem, ChEMBL and RDKit, combining chem-tools and cdx-tools. Resolves compound names, CAS numbers, SMILES, InChIKeys and CIDs; returns molecular weight, formula, GHS hazards, experimental density/boiling point/melting point/flash point/solubility/pKa and vendors; runs substructure (SMARTS) and bioactive-similarity searches and RDKit descriptors; and writes native, editable ChemDraw .cdxml files (captioned structure grids, reaction schemes with arrows, reagents and conditions, multi-step routes) plus SDF, RXN and PNG. Reads .cdxml, .cdx, SDF, MOL and SMILES files. Use this whenever a task names a specific chemical or reagent, asks for a CAS number, molecular weight or hazard, needs a mass-to-volume conversion, wants something drawn in ChemDraw or a figure or scheme for a paper, or asks what is in a ChemDraw file - even if the user does not mention tools, because recalled CAS numbers, masses and hazards are often wrong.
compatibility: Needs Python 3.10+ and internet access to pubchem.ncbi.nlm.nih.gov and www.ebi.ac.uk. RDKit is installed automatically on first use (via uv, or into a private venv in ~/.cache/chem-skills), which needs PyPI access once. SMILES-only work runs offline. In the Claude desktop app, run it as a local MCP server (references/mcp-setup.md).
license: MIT (see LICENSE in https://github.com/Lancifonins/chem-skills)
metadata:
  version: "1.1.0"
---

# chem-suite

One skill for chemistry work: **information tools** (identities, CAS numbers, properties, hazards,
searches) and **ChemDraw tools** (native .cdxml figures and schemes, and reading ChemDraw files).

**If `get_compound_info`, `draw_structures` and the other tools below are already available as MCP
tools** (the chem-suite MCP server, typical in the Claude desktop app), call them directly and skip
the launcher. Drawing results then include a preview image of the structures stored in the file:
look at it before reporting. The server also has `open_in_chemdraw` and `system_check`.

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

The output is JSON on stdout. Exit code 1 means it holds `{"error": ...}`, so read the message and
adjust rather than retrying blindly.

## Step 0: system check (once per session)

Run `check` before the first tool call. The launcher finds a Python 3.10+ with RDKit and installs it
if missing, using uv or a private venv in `~/.cache/chem-skills`. This never modifies the user's own
environments. A first install takes about a minute; tell the user rather than going quiet. In the
report:
- `ready: false`: see "When the tools can't run".
- `network.pubchem` / `network.chembl` false: names, CAS numbers, lookups and searches fail. Only
  SMILES-based work (drawing, `calculate_properties`, file tools) runs offline. Say so.
- `chemdraw.installed`: whether you can offer to open results in ChemDraw.

## When the tools can't run

Sandboxed workspaces (cloud sandboxes, agent VMs) sometimes block PyPI or PubChem. If `check` is not
ready, **stop and tell the user before doing the task**:
- Quote the `problems`, and offer the fixes: run the task in Claude Code on their own computer;
  register the MCP server in the Claude desktop app (`references/mcp-setup.md`); or have an admin
  allow `pypi.org`, `files.pythonhosted.org`, `pubchem.ncbi.nlm.nih.gov` and `www.ebi.ac.uk`.
  `CHEM_SKILLS_PYTHON=/path/to/python` points the launcher at an interpreter that already has RDKit.
- **Don't fill in CAS numbers, masses or hazards from memory**, and **don't fake RDKit or
  hand-place atom coordinates** to get around a failure, unless the user explicitly agrees after
  hearing the risk. Without the tools nothing checks the result, and a wrong CAS number, bond or
  stereocentre looks entirely believable. If the user accepts, label every such value as
  unverified, put `UNVERIFIED` in any filename, and list each structure's SMILES in your reply.

## Tools

**Information**

| Tool | Use it for |
|---|---|
| `get_compound_info` | Identity (name, CAS, CID, formula, MW, SMILES, InChIKey), plus optional `include` sections: `safety`, `physical`, `vendors` |
| `search_substructure` | PubChem compounds containing a SMILES or SMARTS fragment |
| `search_similar_bioactives` | ChEMBL drugs/bioactives similar to a compound |
| `calculate_properties` | Offline RDKit descriptors (logP, TPSA, HBD/HBA, Lipinski) |
| `read_structure_file` | Parse .sdf / .mol / .cdxml / .smi files |

**ChemDraw (native .cdxml)**

| Tool | Makes / reads |
|---|---|
| `draw_structures` | One or many structures as a grid or row, captioned (number / name / CAS / formula / MW) |
| `draw_reaction` | Reaction scheme: `+` between species, arrow, reagents above, conditions and yield below; multi-step via `steps` |
| `convert_to_chemdraw` | .sdf/.mol/.smi → captioned grid; .rxn → reaction scheme |
| `read_chemdraw` | Structures, reaction SMILES and free text from .cdxml or .cdx |

**Other formats**

| Tool | Makes |
|---|---|
| `export_structures` | SDF (one record each, or one side-by-side canvas) for programs other than ChemDraw |
| `draw_structures_image` | Labelled PNG/SVG grid, for slides or a quick look |
| `export_reaction` | MDL .rxn plus a PNG preview |
| `image_to_structure` | DECIMER image recognition (optional dependency) |

When the user says "ChemDraw", a figure for a paper, or a scheme, use the .cdxml tools. They give
proper captions, arrows and editable text, which SDF and RXN can't. Every parameter and output
field is in `references/tools.md`, and ready-made SMARTS for compound classes are in
`references/smarts.md`.

## Looking things up

- **Look things up instead of recalling them.** CAS numbers, molecular weights and hazard codes from
  memory are frequently subtly wrong. CAS numbers returned here are check-digit validated.
- **Ask only for the sections you need.** `get_compound_info` always returns identity. Each
  `include` section costs extra requests: "what's the CAS of X" needs nothing extra, "I'm about to
  use X" warrants `["safety"]`. For several compounds, run one call per compound.
- **Check how each input was read.** Results include `interpreted_as`, plus a `note` when it
  matters. Reagent abbreviations (NBS, DMAP, HATU, DIBAL, ...) resolve to the reagent even though
  many are also valid SMILES. Ambiguous inputs (`CO`, `CN`, `CBS`, `BINAP`, unknown all-letter
  strings with B or P) are refused with an explanation: follow it rather than retrying. A note on a
  short name says which compound PubChem matched, so confirm it's the one the user meant.
- **Report safety data honestly.** GHS lines are aggregated from many depositors, and the percentage
  is the share reporting that hazard. Lead with the signal word and the high-share H-statements, and
  point to the supplier SDS as the authority.
- **Show your work on conversions.** For mass ⇄ volume, fetch `physical` with
  `"properties": ["density"]`, pick a value near room temperature, state its conditions, and show
  the arithmetic. Molarity and equivalents use `molecular_weight`.

## Drawing: identify first, then draw

1. **Identify every compound first** with `get_compound_info`, and check the returned `name` is what
   the user meant. Then draw from the verified SMILES, passing the name for the caption:
   `{"smiles": "<smiles>", "name": "<name the user used>", "label": "3a"}`. Drawing from SMILES
   keeps the exact stereochemistry and skips a second lookup.
2. **"Draw N compounds of class X"**: `search_substructure` with a SMARTS from
   `references/smarts.md`, choose sensible hits (they come in PubChem's order), then
   `draw_structures` with their SMILES and names.
3. **Figures that need data** (MW in a caption, a hazard table, a yield from a mass): get the
   numbers from `get_compound_info` / `calculate_properties`. The drawing tools' `formula` / `mw`
   caption fields suit simple captions; their `cas` field is a best-effort lookup.
4. **Reading a ChemDraw file**: `read_chemdraw` returns SMILES. Pass each to `get_compound_info` to
   name it and get CAS numbers or hazards, or to `calculate_properties` for new compounds.
5. **Structure images from the user**: if you can see the image, read the structure yourself and
   pass the SMILES on. `image_to_structure` is only for image files you cannot view.

## Specifying compounds for drawings

Each compound is a name, CAS number or SMILES string, or an object for full control:

```json
{"smiles": "C[C@H](O)C(=O)O", "label": "3a", "name": "(S)-lactic acid"}
```

- `label` replaces the automatic bold number (use it for "3a", "S1", "ent-7").
- `name` sets the caption text. Otherwise the caption uses the input as written, or a PubChem title
  for SMILES inputs.
- Pass verified structures as `{"smiles": "..."}`: drawn exactly as given, with no guessing. Stereo in
  the SMILES (`@`/`@@`, `/`/`\`) becomes wedges and hashes.
- Plain strings are auto-detected; check each compound's `interpreted_as` and the result's `notes`.
- Unresolvable compounds are listed under `failed` and the rest are still drawn. Tell the user.
- Files are never overwritten: a repeated `filename` gets a -2, -3... suffix, so always report the
  returned path. Pass `"overwrite": true` to deliberately replace a file.

## Drawing reaction schemes well

- Reagents go above the arrow as text by default, and formula-like tokens get proper subscripts
  (`H2SO4`, `Pd(PPh3)4`, `Et3N`). Write them the way a chemist would, e.g.
  `"reagents": ["Pd(PPh3)4 (5 mol%)", "K2CO3"]`. Use `reagents_as: "structures"` only when the
  reagent's structure is the point.
- `conditions` go below the arrow. `;` or a newline starts a new line: `"dioxane/H2O, 90 °C; 12 h"`.
  Add `yield_text` (or `yield` per step) as its own line.
- For a linear route, give `reactants` (the starting materials) plus `steps`. Each step's `products`
  become the next step's starting point, and compound numbers run on through the scheme. Only
  include by-products (H2O, HCl) if the user wants them shown.
- The default caption is bold numbers only, the usual style for papers. Use `number_name` for
  teaching slides, and `none` when the user will number compounds themselves.

## Files

Give the user the full output path. On macOS, `open <path>` opens a .cdxml in ChemDraw, but only
do that if they ask or would clearly want it. Everything in a .cdxml is native ChemDraw objects, so
the user can restyle it (e.g. apply their journal's document settings) and edit it there. Very long
single-row schemes run wide: split long routes into several `draw_reaction` calls. Change the
locations with `CHEM_EXPORT_DIR` (outputs) and `CHEM_WORKDIR` (allowed input root). Paths outside
the input root are refused.

When reading ChemDraw files, read multi-step reactions from the `text` and structures, because
RDKit's reaction reader can merge an intermediate shared by two steps. Salts come back as one
dot-separated SMILES.

## Examples

```bash
bash scripts/chem get_compound_info '{"identifier": "dichloromethane", "include": ["safety"]}'
bash scripts/chem get_compound_info '{"identifier": "THF", "include": ["physical"], "properties": ["density"]}'
bash scripts/chem search_substructure '{"query": "c[OX2H]", "query_type": "smarts", "max_results": 8}'
bash scripts/chem draw_structures '{"compounds": ["caffeine", {"smiles": "C[C@H](N)C(=O)O", "name": "L-alanine"}], "caption": "number_name"}'
bash scripts/chem draw_reaction '{"reactants": ["benzene", "nitric acid"], "products": ["nitrobenzene"], "reagents": ["H2SO4"], "conditions": "50 °C; 1 h", "yield_text": "85%"}'
bash scripts/chem read_chemdraw drawings/scheme1.cdxml
```

## Reporting problems

Failed tool calls are logged locally (see `error_log` in `check`). If a tool returns an error that
looks like a bug rather than bad input (an exception name like `KeyError:` or `Bad arguments`, or
output that is plainly wrong), run `bash <skill-dir>/scripts/chem report`. Show the user the Markdown
it prints: it has the skill version, the environment check and the recent failures with tracebacks,
ready to send to the skill's author. Set `CHEM_SKILLS_DEBUG=1` to log successful calls too.
`bash <skill-dir>/scripts/chem version` prints the installed version.
