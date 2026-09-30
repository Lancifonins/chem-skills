# Changelog

Versions are per skill (`metadata.version` in each SKILL.md).

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
