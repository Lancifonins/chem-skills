# Tool reference

Generated from `scripts/tool_schemas.py`. `scripts/cdx schema <tool>` prints the raw JSON schema.

A *compound* is a string (name, CAS number, reagent abbreviation or SMILES, auto-detected) or an object:
`{"smiles": "..."}` (exact, never guessed; prefer this) or `{"structure": "...", "identifier_type": "name"}`,
each with optional `"label": "3a"` (bold compound number) and `"name": "..."` (caption text).

Outputs list each compound's `interpreted_as`, and a `notes` list explains any input that was read
in a non-obvious way (e.g. 'NBS' as N-bromosuccinimide). Ambiguous inputs such as `CO` (methanol or
carbon monoxide) or `CBS` (which enantiomer?) are refused with an explanation instead of guessed.
A `warnings` list reports any text characters ChemDraw's fonts cannot show. Files are never
overwritten unless `overwrite` is true: a -2, -3... suffix is added instead.

## draw_structures

Draw one or more compounds into a native, editable ChemDraw .cdxml file, laid out as a grid or a single row, with captions under each structure (bold compound numbers, names, CAS, formula, MW). Stereochemistry is drawn with wedges. Use separate_files for one file per compound.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `compounds` | array of compounds | yes |  |
| `layout` | string | no | One of: `grid`, `row`. |
| `columns` | integer | no | Grid columns (default 4). |
| `caption` | string | no | Caption lines under each structure: any of 'number', 'name', 'cas', 'formula', 'mw' joined by '_' (e.g. 'number_name'), or 'none'. |
| `number_start` | integer | no | First automatic compound number. |
| `filename` | string | no | Output file stem; '.cdxml' is added. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |
| `separate_files` | boolean | no |  |

**Output:** `path` (or `paths` with `separate_files`), `layout`, `compounds` (input, SMILES, formula, label if custom) and `failed`.

## draw_reaction

Draw a reaction scheme into a native ChemDraw .cdxml file: structures joined by '+', a real reaction arrow with reagents above it and conditions/yield below, compound numbers underneath, and ChemDraw reaction-step metadata. Single step: reactants + products (+ reagents, conditions, yield_text). Linear multi-step route: reactants (starting materials) + steps, each step's products becoming the next step's starting point.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `reactants` | array of compounds | yes |  |
| `products` | array of compounds | no |  |
| `reagents` | array of compounds | no | Written above the arrow, as text (default) or structures. |
| `conditions` | string | no | Below the arrow; ';' or newline starts a new line, e.g. 'THF, 0 °C; 2 h'. |
| `yield_text` | string | no | e.g. '85%'; shown under the conditions. |
| `steps` | array of object | no | Multi-step route. When given, 'products'/'reagents'/'conditions'/'yield_text' are ignored. Each step: `products` (required), `reagents`, `conditions`, `yield`. |
| `caption` | string | no | Caption lines under each structure: any of 'number', 'name', 'cas', 'formula', 'mw' joined by '_' (e.g. 'number_name'), or 'none'. |
| `number_start` | integer | no |  |
| `reagents_as` | string | no | 'text' writes reagent names (formulas get subscripts); 'structures' draws them. One of: `text`, `structures`. |
| `filename` | string | no | Output file stem; '.cdxml' is added. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |

**Output:** `path`, `steps`, `reaction_smiles` (one per step, reagents omitted), `compounds` (per stage) and `failed`. The file holds ChemDraw reaction-step metadata linking reactants, products, arrow and the objects above/below it, so ChemDraw's reaction tools recognise the scheme.

## convert_to_chemdraw

Convert a structure file into a ChemDraw .cdxml document: .sdf/.mol/.smi become a captioned grid (SDF titles and SMILES-file names are used as captions); .rxn becomes a reaction scheme with an arrow.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `path` | string | yes | Input file, relative to the working directory. |
| `layout` | string | no | One of: `grid`, `row`. |
| `columns` | integer | no |  |
| `caption` | string | no | Caption lines under each structure: any of 'number', 'name', 'cas', 'formula', 'mw' joined by '_' (e.g. 'number_name'), or 'none'. |
| `filename` | string | no | Output file stem; '.cdxml' is added. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |

**Output:** Same as `draw_structures` for structure files, or `draw_reaction` for .rxn files (agents are drawn as structures above the arrow). SDF `_Name` titles and names in the second column of a .smi file become captions.

## read_chemdraw

Read a ChemDraw .cdxml or binary .cdx file: returns every structure (SMILES, formula, MW, InChIKey), reaction SMILES for drawn reaction steps, and free text such as captions and conditions (.cdxml only).

| Parameter | Type | Required | Details |
|---|---|---|---|
| `path` | string | yes | File relative to the working directory. |
| `max_structures` | integer | no |  |

**Output:** `structure_count`, `structures` (`index`, `smiles`, `formula`, `molecular_weight`, `inchikey`), `reactions` (reaction SMILES; a shared intermediate in multi-step schemes may be merged) and `text` (free text blocks, .cdxml only; newlines separate caption lines).

## File details

- Drawing settings follow ACS Document 1996: 14.4 pt bonds, Arial 10 pt labels, 0.6 pt lines.
- Heteroatom labels carry explicit hydrogen counts and charges, and put H on the side away from the bonds (`HO`, `H2N`).
- Output is Kekulé form; aromatic rings are drawn with alternating double bonds.
- Every written file is re-read with RDKit before the tool returns, and a file that fails to parse is reported as an error.
