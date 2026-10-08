# Changelog

Versions are per skill (`metadata.version` in each SKILL.md).

## chem-tools 1.1.0 / cdx-tools 1.1.0 / chem-suite 1.1.0

Fixes for problems found in real use: inputs are never silently misread, files are never silently
overwritten, and ChemDraw text follows ChemDraw's own conventions.

- **Reagent abbreviations are no longer drawn as the wrong molecule.** `NBS`, `NIS`, `BOP` and other
  abbreviations are also valid SMILES (`NBS` became H2N-BH-SH). A table of 86 reagents generated from
  PubChem (`tools/gen_reagents.py`) now resolves them, offline. Ambiguous inputs are refused with an
  explanation: `CBS`, `BINAP` and `CSA` (which enantiomer?), `CO`, `NO`, `CN`, `CS` and `SO` (formula or SMILES?),
  `Boc` and `Bn` (groups, not compounds), and unknown all-letter strings containing B or P.
- Every result reports how each input was read (`interpreted_as`, `note`). Short names looked up in
  PubChem name the compound they matched, because PubChem synonyms sometimes hit unrelated compounds.
- Drawing tools accept `{"smiles": ...}` (exact, never guessed) and `identifier_type`. Structures
  read from files are passed as exact SMILES.
- **Broken SMILES report RDKit's reason** (e.g. "extra open parentheses near character 5") instead
  of a misleading "PubChem has no compound" error.
- **Files are never overwritten**: a repeated filename gets a -2, -3... suffix unless `overwrite`
  is true. With `separate_files`, structures given as SMILES are named by InChIKey, so stereoisomers
  no longer replace each other.
- **ChemDraw labels**: charges are written ChemDraw's way (`N+`, `O-` in formula style), so the minus no
  longer shows as `?`. Multiple charges and isotope numbers are true superscripts (superscript was
  written as subscript before). Isotopes are placed before their element (H3(13)C), and radicals are
  drawn by ChemDraw instead of a `•` text glyph.
- **ChemDraw text** is kept to characters the fonts can show: Greek goes through the Symbol font,
  dashes, minus signs and arrows are converted, and anything else is reported in `warnings`.

## chem-suite 1.0.0

- New all-in-one skill with every chem-tools and cdx-tools tool, one launcher (`scripts/chem`), one
  system check and one MCP server. Generated from the two skills by `tools/assemble_suite.py`, so
  it always ships the same tool code.

## chem-tools 1.0.0 / cdx-tools 1.0.0

First shareable release.

- **chem-tools:** `get_compound_info` (identity + optional safety / physical / vendors sections),
  `search_substructure`, `search_similar_bioactives`, `calculate_properties`, `read_structure_file`,
  `export_structures`, `draw_structures_image`, `export_reaction`, `image_to_structure`.
- **cdx-tools:** `draw_structures`, `draw_reaction` (single and multi-step), `convert_to_chemdraw`,
  `read_chemdraw`, writing native ChemDraw CDXML.
- Launchers run with `bash`, find or install RDKit automatically (uv or a private venv shared by both
  skills), and never write to stdout in MCP mode.
- `check`, `version` and `report` commands, plus a local error log for bug reports.
- Local MCP servers (`bash scripts/<launcher> mcp`) for the Claude desktop app. cdx-tools adds
  `open_in_chemdraw` and returns a preview image with every drawing.
- SKILL.md rules: stop and ask when the tools can't run; never hand-build structures or fill in
  CAS numbers or hazards from memory without labelling them as unverified.
