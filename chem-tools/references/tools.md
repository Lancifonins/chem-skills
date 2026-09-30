# Tool reference

Generated from `scripts/tool_schemas.py`. Run `scripts/chem schema <tool>` for the raw JSON schema.

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
| `identifier_type` | string | no | Leave as 'auto' unless detection guesses wrong. Auto treats any space-free string RDKit can parse as SMILES ('CO' = methanol). One of: `auto`, `name`, `cas`, `smiles`, `inchi`, `inchikey`, `cid`. |
| `properties` | array of string | no | Physical properties for the 'physical' section. Defaults to density, boiling, melting and flash point. One of: `density`, `boiling_point`, `melting_point`, `flash_point`, `solubility`, `vapor_pressure`, `refractive_index`, `pka`. |
| `max_values` | integer | no | Max reported values per physical property (default 4). Range 1–10. |
| `max_vendors` | integer | no | Max vendors listed in the 'vendors' section (default 15). Range 1–50. |

**Output:** Always returns identity: `name`, `iupac_name`, `cas_number` (check-digit validated; `null` if PubChem lists none), `other_cas_numbers` (deprecated/alternate), `pubchem_cid`, `formula`, `molecular_weight`, `exact_mass`, `smiles`, `inchikey`, `xlogp`, `tpsa`, `formal_charge`, `pubchem_url`.

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
| `image` | boolean | no | Also write a PNG preview (default true). |

**Output:** Returns `rxn_path`, `reaction_smiles`, `image_path` (PNG preview) and `failed`. Reagents are written as agents, and ChemDraw draws them above the arrow. Stoichiometry and atom mapping are not included.

## image_to_structure

Recognise a chemical structure in an image file with DECIMER and look it up in PubChem. Only needed when the image cannot be sent to Claude directly; requires DECIMER.

| Parameter | Type | Required | Details |
|---|---|---|---|
| `image_path` | string | yes | Image path relative to the working directory. |
| `lookup` | boolean | no | Also look the structure up in PubChem (default true). |

**Output:** Needs the optional `decimer` package (heavy: TensorFlow). Returns `predicted` (SMILES, formula, ...) plus `pubchem_match` (the same fields as `get_compound_info` identity). Always double-check stereochemistry.
