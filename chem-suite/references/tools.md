# Tool reference

## Part 1: information tools

Generated from `scripts/tool_schemas.py`. Run `bash scripts/chem schema <tool>` for the raw JSON schema.

## How inputs are read

Every structure input goes through one resolver, and results report how each one was read
(`interpreted_as`, plus a `note` when it matters):

- **Reagent abbreviations** (about 90: NBS, NIS, DMAP, HATU, BOP, DIBAL, mCPBA, DMF, dppf, ...) resolve
  to the reagent, offline. Many are also valid SMILES (`NBS` would otherwise become H2N-BH-SH).
- **Ambiguous inputs are refused** with an explanation rather than guessed: stereo-ambiguous reagents
  (`CBS`, `BINAP`, `CSA`), two-letter formulas that are also SMILES (`CO`, `NO`, `CN`, `CS`, `SO`), protecting
  groups (`Boc`, `Bn`), and unknown all-letter strings containing B or P.
- **Other all-letter SMILES** (`CCO`) are accepted, with a note giving the formula.
- **Short names** (6 characters or fewer) looked up in PubChem come with a note naming the matched compound,
  because PubChem synonyms sometimes match unrelated compounds.
- **Broken SMILES** return RDKit's reason, e.g. "extra open parentheses near character 5".

Force a reading with `identifier_type`, or for drawings pass `{"smiles": ...}`.

## Contents

- [get_compound_info](#get_compound_info)
- [search_substructure](#search_substructure)
- [search_similar_bioactives](#search_similar_bioactives)
- [calculate_properties](#calculate_properties)
- [read_structure_file](#read_structure_file)
- [export_structures](#export_structures)
- [draw_structures_image](#draw_structures_image)
- [export_reaction](#export_reaction)
- [image_to_structure](#image_to_structure)

## get_compound_info

Look up a compound in PubChem. Always returns identity: name, IUPAC name, check-digit-validated CAS number, CID, formula, molecular weight, exact mass, SMILES, InChIKey, XLogP, TPSA and a PubChem link. Add sections with `include`: 'safety' (GHS signal word, pictograms, all H-statements with the share of notifiers reporting each, P-codes), 'physical' (verbatim experimental density, boiling/melting/flash point, solubility, vapour pressure, refractive index, pKa), 'vendors' (chemical vendors listed in PubChem with catalogue links; no prices or stock). Request only the sections the question needs, and use this instead of recalling CAS numbers, masses or hazards.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `identifier` | string | yes | Compound name, CAS number (e.g. '64-17-5'), SMILES, InChIKey, or PubChem CID. |
| `include` | array of string | no | Extra sections to fetch. Omit for identity only. Use 'safety' whenever the user will handle the compound; 'physical' for mass/volume conversions. One of: `safety`, `physical`, `vendors`. |
| `identifier_type` | string | no | Leave as 'auto': it checks reagent abbreviations (NBS, DMAP, ...) and refuses ambiguous inputs such as 'CO' (methanol or cobalt) with an explanation. Set it to force one reading. One of: `auto`, `name`, `cas`, `smiles`, `inchi`, `inchikey`, `cid`, `abbreviation`. |
| `properties` | array of string | no | Physical properties for the 'physical' section. Defaults to density, boiling, melting and flash point. One of: `density`, `boiling_point`, `melting_point`, `flash_point`, `solubility`, `vapor_pressure`, `refractive_index`, `pka`. |
| `max_values` | integer | no | Max reported values per physical property (default 4). Range 1–10. |
| `max_vendors` | integer | no | Max vendors listed in the 'vendors' section (default 15). Range 1–50. |

**Output:** Always returns identity: `interpreted_as` (and `note` when relevant), `name`, `iupac_name`, `cas_number` (check-digit validated; `null` if PubChem lists none), `other_cas_numbers` (deprecated/alternate), `pubchem_cid`, `formula`, `molecular_weight`, `exact_mass`, `smiles`, `inchikey`, `xlogp`, `tpsa`, `formal_charge`, `pubchem_url`.

Optional sections (each costs extra PubChem requests; a failed section becomes `{"error": ...}` and the rest still return):
- `safety`: `ghs_available`, `signal_word`, `pictograms`, `hazard_statements` (e.g. `"H319 (37.7%): ..."`, where the percentage is the share of notifiers reporting it; unannotated lines are from single sources), `precautionary_codes`, `source_url`.
- `physical`: `experimental_values` maps each requested property to verbatim strings with units and conditions (e.g. `"0.8833 g/cu cm at 25 °C"`), or `null` if PubChem has none.
- `vendors`: `commercially_available`, `vendor_count`, `vendors` (`name`, `url`), `pubchem_vendors_url`. No prices or stock.

## search_substructure

Find PubChem compounds containing a substructure. Accepts SMILES, or SMARTS for compound classes (e.g. alpha-amino acids: '[NX3;!$(N-C=O)][CX4][CX3](=O)[OX2H1,OX1-]', phenols: 'c[OX2H]'). Returns names, CIDs, formulas and SMILES.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `query` | string | yes | Substructure as SMILES or SMARTS. |
| `query_type` | string | no | One of: `smiles`, `smarts`. |
| `max_results` | integer | no | Range 1–50. |
| `include_cas` | boolean | no | Also resolve CAS numbers (one extra request per hit; default false). |

**Output:** Returns `matches` with `name`, `pubchem_cid`, `formula`, `molecular_weight`, `smiles` (and `cas_number` if requested). Hits are in PubChem's order, not by similarity. See `smarts.md`.

## search_similar_bioactives

Search ChEMBL for bioactive molecules and drugs structurally similar (Tanimoto) to a compound. Returns ChEMBL IDs, names, similarity, max clinical phase and SMILES.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `identifier` | string | yes | Compound name, CAS number (e.g. '64-17-5'), SMILES, InChIKey, or PubChem CID. |
| `similarity_threshold` | integer | no | Minimum similarity percent (default 80). Range 40–100. |
| `max_results` | integer | no | Range 1–50. |

**Output:** Returns `results` with `chembl_id`, `name` (often `null` for research compounds), `similarity` (percent), `max_clinical_phase` (4 = approved drug), `smiles`, `url`. Salts and prodrugs of the query often appear at 100%.

## calculate_properties

Compute properties locally with RDKit: formula, MW, exact mass, InChIKey, Crippen logP, TPSA, H-bond donors/acceptors, rotatable bonds, rings, Fsp3, stereocentres and Lipinski violations. Works offline for SMILES; use it for drawn/novel structures not in PubChem.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `identifier` | string | yes | Compound name, CAS number (e.g. '64-17-5'), SMILES, InChIKey, or PubChem CID. |

**Output:** Local RDKit, so it's instant and works offline for SMILES (names still need one PubChem lookup). `logp_crippen` is an estimate and differs from PubChem's `xlogp`. Lipinski violations count MW > 500, logP > 5, HBD > 5, HBA > 10.

## read_structure_file

Read structures from a local .sdf, .mol, .cdxml or .smi file (path relative to the working directory) and return SMILES, formula, MW and InChIKey for every structure. Several drawings on one ChemDraw canvas are returned separately.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `path` | string | yes | e.g. 'input_files/single_mol_file.sdf' |
| `max_molecules` | integer | no | Range 1–500. |

**Output:** Each structure gets `record`, `smiles`, `formula`, `molecular_weight`, `exact_mass`, `inchikey` and `title` if present. Separate fragments on one canvas (or salts) are split into separate entries. Binary `.cdx` is unsupported, so re-save it as `.cdxml` or `.sdf`.

## export_structures

Write compounds to an SDF file that opens in ChemDraw. layout='separate' writes one record per compound; 'single_canvas' puts them side by side in one drawing.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `compounds` | array of string | yes | Compounds as names, CAS numbers, or SMILES (can be mixed). |
| `filename` | string | no | Output file stem; the extension is added automatically. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |
| `layout` | string | no | One of: `separate`, `single_canvas`. |

**Output:** Returns `path`, `exported` and `failed` (unresolvable inputs are reported, not fatal).

## draw_structures_image

Render compounds as a labelled grid image (PNG or SVG). Legends can combine index, name, CAS and formula, e.g. 'index_name_cas'.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `compounds` | array of string | yes | Compounds as names, CAS numbers, or SMILES (can be mixed). |
| `legend` | string | no | Any combination of 'index', 'name', 'cas', 'formula' joined by '_'. Default 'name'. |
| `columns` | integer | no | Range 1–10. |
| `filename` | string | no | Output file stem; the extension is added automatically. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |
| `image_format` | string | no | One of: `png`, `svg`. |

**Output:** Returns `path`, `legends` and `failed`. The legend uses the text exactly as given, so pass the names the user wants shown.

## export_reaction

Write a reaction scheme as an MDL .rxn file (opens in ChemDraw with a reaction arrow; reagents go above the arrow) plus a PNG preview, and return the reaction SMILES.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `reactants` | array of string | yes | Compounds as names, CAS numbers, or SMILES (can be mixed). |
| `products` | array of string | yes | Compounds as names, CAS numbers, or SMILES (can be mixed). |
| `reagents` | array of string | no | Catalysts, reagents or solvents shown over the arrow. |
| `filename` | string | no | Output file stem; the extension is added automatically. |
| `overwrite` | boolean | no | Replace an existing file with the same name. By default a -2, -3... suffix is added instead, so earlier files are never lost. |
| `image` | boolean | no | Also write a PNG preview (default true). |

**Output:** Returns `rxn_path`, `reaction_smiles`, `image_path` (PNG preview) and `failed`. Reagents are written as agents, and ChemDraw draws them above the arrow. Stoichiometry and atom mapping are not included.

## image_to_structure

Recognise a chemical structure in an image file with DECIMER and look it up in PubChem. Only needed when the image cannot be sent to Claude directly; requires DECIMER.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `image_path` | string | yes | Image path relative to the working directory. |
| `lookup` | boolean | no | Also look the structure up in PubChem (default true). |

**Output:** Needs the optional `decimer` package (heavy: TensorFlow). Returns `predicted` (SMILES, formula, ...) plus `pubchem_match` (the same fields as `get_compound_info` identity). Always double-check stereochemistry.

---

# Part 2: ChemDraw tools

Generated from `scripts/tool_schemas.py`. `bash scripts/chem schema <tool>` prints the raw JSON schema.

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
