---
name: cdx-tools
description: Create and read native ChemDraw files. Writes editable .cdxml documents directly - single structures, captioned grids with bold compound numbers, and reaction schemes with real arrows, reagents above and conditions/yields below, including multi-step routes - from compound names, CAS numbers or SMILES. Converts SDF/MOL/SMILES/RXN files to ChemDraw, and extracts structures, reaction SMILES and text from .cdxml or binary .cdx files. Use this whenever the user wants something drawn "in ChemDraw", a .cdx/.cdxml file, a figure or scheme for a paper, SI or group meeting, a compound table with numbering, or asks what is in a ChemDraw file - even if they only say "draw" or "make a scheme".
compatibility: Needs Python 3.10+. RDKit is installed automatically on first use (via uv, or into a private venv in ~/.cache/chem-skills), which needs PyPI access once. Compound names/CAS need pubchem.ncbi.nlm.nih.gov; SMILES work offline. In the Claude desktop app, run it as a local MCP server (references/mcp-setup.md). Works best alongside the chem-tools skill.
license: MIT (see LICENSE in https://github.com/Lancifonins/chem-skills)
metadata:
  version: "1.1.0"
---

# cdx-tools

This skill **draws and reads ChemDraw files**. It is the drawing half of a pair: the
**chem-tools** skill is the information half (identities, CAS numbers, properties, hazards,
searches). Use chem-tools for anything that is a *chemistry question*, and cdx-tools for turning
the answer into a ChemDraw document.

**If `draw_structures` and the other tools below are already available as MCP tools** (the
cdx-tools MCP server, typical in the Claude desktop app), call them directly and skip the launcher.
They are the same tools running natively on the user's machine. Each drawing result then includes
a preview image of the structures stored in the file: look at it before reporting. The server also
has `open_in_chemdraw` and `cdx_system_check`.

Otherwise every tool runs through one launcher. Always call it with `bash`, because the executable
bit is often lost when a skill is installed. Run it from the user's working directory: files are
written to `./exports` there, and input paths resolve from there.

```bash
bash <skill-dir>/scripts/cdx check                              # system check - run first
bash <skill-dir>/scripts/cdx <tool> '<json input>'
bash <skill-dir>/scripts/cdx read_chemdraw path/to/file.cdxml   # shorthand for the first required field
bash <skill-dir>/scripts/cdx list                               # all tools
bash <skill-dir>/scripts/cdx schema <tool>                      # exact JSON input schema
```

The output is JSON. Exit code 1 means it holds `{"error": ...}`.

## Step 0: system check (once per session)

Run `check` before the first drawing in a session. The launcher finds a Python 3.10+ with RDKit and
installs RDKit if none has it, using uv or a private venv in `~/.cache/chem-skills` (shared with
chem-tools). This never modifies the user's own environments. A first install takes about a
minute and prints progress to stderr, so tell the user what's happening instead of letting the
pause look like a hang.

Read the report:
- `ready: false`: stop and follow "When the tools can't run" below.
- `network.pubchem: false`: only SMILES inputs will work. Say so, and use SMILES.
- `chem_tools.found`/`runs`: whether the chem-tools workflow below is available, and the
  `command` to call it with.
- `chemdraw.installed`: whether you can offer to open results in ChemDraw.

## When the tools can't run

Sandboxed workspaces (cloud sandboxes, agent VMs) sometimes block PyPI, so RDKit can't be
installed. If `check` is not ready, **stop and tell the user before drawing anything**:
- Quote the `problems`, and offer the fixes: run the task in Claude Code on their own computer
  (the tools work there as designed); register the local MCP server in the Claude desktop app
  (`references/mcp-setup.md`); or have an admin allow `pypi.org`, `files.pythonhosted.org` and
  `pubchem.ncbi.nlm.nih.gov`. `CHEM_SKILLS_PYTHON=/path/to/python` points the launcher at an
  interpreter that already has RDKit.
- **Don't fake RDKit or hand-place atom coordinates to get around it** unless the user explicitly
  agrees after hearing the risk. Without RDKit nothing checks the structures, and a wrong bond,
  charge or stereocentre in a ChemDraw figure looks entirely believable. If the user accepts,
  put `UNVERIFIED` in each filename and list every structure's SMILES in your reply so they can
  check them.

| Tool | Makes / reads |
|---|---|
| `draw_structures` | One or many structures as a grid or row, captioned (number / name / CAS / formula / MW); `separate_files` for one file each |
| `draw_reaction` | Reaction scheme: `+` between species, arrow, reagents above, conditions and yield below, numbered compounds; multi-step via `steps` |
| `convert_to_chemdraw` | .sdf/.mol/.smi → captioned grid; .rxn → reaction scheme |
| `read_chemdraw` | Structures, reaction SMILES and free text from .cdxml or .cdx |

The full parameter and output list is in `references/tools.md`.

## Use chem-tools for the chemistry, cdx-tools for the drawing

cdx-tools can turn a name into a structure by itself, but it doesn't check that PubChem picked
the compound the user meant, and it has no properties, hazards or search. So route the chemistry
through chem-tools: use its MCP tools if present, otherwise load that skill or run the
`chem_tools.command` from `cdx check`.

1. **Identify every compound first** with chem-tools `get_compound_info`. Check that the returned
   `name` is what the user meant, since short or trivial names can resolve to something else.
   Then draw from the verified SMILES, passing the name for the caption:
   `{"smiles": "<smiles from chem-tools>", "name": "<name the user used>", "label": "3a"}`.
   Drawing from SMILES also keeps the exact stereochemistry and skips a second lookup.
2. **"Draw N compounds of class X"**: run chem-tools `search_substructure` (it has ready-made
   SMARTS), choose sensible hits, then `draw_structures` with their SMILES and names.
3. **Figures that need data** (a caption with MW, a table of hazards, a yield from a mass): get
   the numbers from chem-tools (`get_compound_info`, `calculate_properties`). Use cdx-tools'
   `formula`/`mw` caption fields only for simple captions; its `cas` field is a best-effort
   PubChem lookup.
4. **Reading a ChemDraw file**: `read_chemdraw` returns SMILES only. Pass each SMILES to
   chem-tools `get_compound_info` to name it and get CAS numbers or hazards, or to
   `calculate_properties` for descriptors of new compounds that aren't in PubChem.
5. **If chem-tools is unavailable** (per `cdx check`), carry on with cdx-tools' built-in lookup
   for names and CAS numbers, and tell the user that property, hazard and search questions need
   chem-tools installed.

## Specifying compounds

Each compound is a name, CAS number or SMILES string, or an object for full control:

```json
{"smiles": "C[C@H](O)C(=O)O", "label": "3a", "name": "(S)-lactic acid"}
```

- `label` replaces the automatic bold number (use it for "3a", "S1", "ent-7").
- `name` sets the caption text. Otherwise the caption uses the input as written, or a PubChem
  title for SMILES inputs.
- Pass verified structures as `{"smiles": "..."}`: drawn exactly as given, with no guessing. Write
  the stereo into the SMILES (`@`/`@@`, `/`/`\`) and it becomes wedges and hashes.
- Plain strings are auto-detected. Reagent abbreviations (NBS, DMAP, ...) resolve to the reagent, and
  ambiguous inputs (`CO`, `CBS`, unknown all-letter strings with B or P) are refused with an
  explanation. Check each compound's `interpreted_as` and the `notes` list in the result.
- Unresolvable compounds are listed under `failed` and the rest are still drawn. Tell the user.
- Files are never overwritten: a second drawing with the same `filename` gets a -2, -3... suffix,
  so always report the returned path. Pass `"overwrite": true` to deliberately replace a file.

## Drawing reaction schemes well

- Reagents go above the arrow as text by default, and tokens that look like formulas get proper
  subscripts (`H2SO4`, `Pd(PPh3)4`, `Et3N`). Write them the way a chemist would, e.g.
  `"reagents": ["Pd(PPh3)4 (5 mol%)", "K2CO3"]`. Use `reagents_as: "structures"` only when the
  reagent's structure is the point (a new ligand or catalyst).
- `conditions` go below the arrow. `;` or a newline starts a new line: `"dioxane/H2O, 90 °C; 12 h"`.
  Add `yield_text` (or `yield` per step) as its own line.
- For a linear route, give `reactants` (the starting materials) plus `steps`. Each step's
  `products` become the next step's starting point, and compound numbers run on through the whole
  scheme. Only include by-products (H2O, HCl) if the user wants them shown.
- The default caption is bold numbers only, the usual style for papers. Use `number_name` for
  teaching slides, and `none` when the user will number compounds themselves.

## After writing a file

Give the user the path. On macOS, `open <path>` opens it in ChemDraw, but only do that if they ask
or would clearly want it. Everything in the file is native ChemDraw objects, so they can restyle
it (e.g. apply their journal's document settings) and move, edit or clean up structures there.
Layout is automatic: very long single-row schemes run wide, so split long routes into several
`draw_reaction` calls or suggest a wrap to the user.

## Reading ChemDraw files

`read_chemdraw` returns each structure's SMILES, formula, MW and InChIKey, reaction SMILES for
drawn reaction steps, and free text (captions, conditions) for .cdxml. Binary .cdx gives structures
only. Two caveats:
- Read multi-step reactions from the `text` and structures. RDKit's reaction reader can merge an
  intermediate that is shared by two steps.
- Salts and multi-component drawings come back as one dot-separated SMILES.

## Reporting problems

Failed tool calls are logged locally (see `error_log` in `check`). If a tool returns an error that
looks like a bug rather than bad input (an exception name like `KeyError:` or `Bad arguments`, or
output that is plainly wrong), run `bash <skill-dir>/scripts/cdx report`. Show the user the
Markdown it prints: it has the skill version, the environment check and the recent failures with
tracebacks, ready to send to the skill's author. Set `CHEM_SKILLS_DEBUG=1` to log successful calls
too. `bash <skill-dir>/scripts/cdx version` prints the installed version.
